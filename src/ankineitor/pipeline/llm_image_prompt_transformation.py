import hashlib
import json
from typing import Any, Dict, List, Optional, Type

import pandas as pd
from google.genai import types as genai_types
from loguru import logger
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential
from tqdm import tqdm

from ..config import get_settings
from ..security.exceptions import ValidationError
from .db_client import SQLAlchemyClient
from .llm_auth import (
    normalize_token as _normalize_token,
    resolve_model_name as _resolve_model_name,
)
from .llm_client_factory import (
    GenAIClientConfig,
    build_genai_client as _build_genai_client_shared,
    resolve_vertex_credentials as _resolve_vertex_credentials_shared,
)
from .transformations import Transformation

DEFAULT_IMAGE_PROMPT_MODEL = "gemini-3.1-pro-preview"
DEFAULT_IMAGE_DO_NOT_GENERATE_TERMS = [
    "与",
    "一个",
    "不会",
    "而",
    "于",
    "以",
    "以及",
    "想要",
    "觉",
    "之",
    "之中",
    "可",
    "心头",
    "一阵",
    "难以",
    "大半夜",
    "嘶",
    "看来",
    "将",
    "下意识",
    "这时",
    "下方",
    "一下",
    "连通",
    "半个",
]
MASTER_IMAGE_PROMPT_TEMPLATE = (
    "A highly detailed, conceptual illustration specifically designed as a language learning "
    "vocabulary flashcard. The central image visually represents:\n\n"
    "{visual_description}\n\n"
    ".\n\n"
    "Style Requirements: A strong Victorian gaslamp fantasy aesthetic. The object should feature "
    "ornate gothic details, tarnished brass, dark mahogany, and intricate engravings. Use a moody, "
    "rich color palette with dramatic, high-contrast rim lighting to make the subject look "
    "three-dimensional and premium.\n\n"
    "Background & Framing: The subject must be strictly isolated and centered tightly on a solid, "
    "uniform, pale aged-ivory background (hex code #F8F5EE) to ensure maximum contrast.\n\n"
    "Formatting & Constraints: The image must be strictly a 1:1 square aspect ratio. The image is "
    "COMPLETELY TEXT-FREE: absolutely no letters, no Chinese characters, no words, no labels, "
    "no speech bubbles, and no signage. Purely a visual representation."
)
ALLOWED_IMAGE_TERM_TYPES = {
    "concrete_noun",
    "verb_action",
    "abstract_grammar",
    "proper_noun",
}


class VisualPromptPayload(BaseModel):
    """Structured model for stage-1 visual prompt generation."""

    image_term_type: str = Field(
        description=(
            "One of: concrete_noun, verb_action, abstract_grammar, proper_noun."
        )
    )
    visual_description: str = Field(
        description=(
            "An evocative, concrete English visual description for the image subject."
        )
    )


def _normalize_blocked_term(value: Optional[str]) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_image_term_type(value: Optional[str]) -> str:
    normalized = (value or "").strip().lower().replace("-", "_").replace(" ", "_")
    alias_map = {
        "noun": "concrete_noun",
        "object": "concrete_noun",
        "concrete": "concrete_noun",
        "concrete_object": "concrete_noun",
        "verb": "verb_action",
        "action": "verb_action",
        "verb_or_action": "verb_action",
        "abstract": "abstract_grammar",
        "grammar": "abstract_grammar",
        "adjective": "abstract_grammar",
        "adverb": "abstract_grammar",
        "proper": "proper_noun",
        "propername": "proper_noun",
        "proper_name": "proper_noun",
    }
    normalized = alias_map.get(normalized, normalized)
    if normalized in ALLOWED_IMAGE_TERM_TYPES:
        return normalized
    return "abstract_grammar"


def _normalize_language_name(language: Optional[str]) -> str:
    if not language:
        return ""
    return "".join(ch for ch in str(language).strip().lower() if ch.isalnum())


class LLMImagePromptTransformation(Transformation):
    """
    Stage 1: builds a strict master image prompt from each vocabulary word.
    """

    pipeline_stage = "llm"

    def __init__(
        self,
        db_client: SQLAlchemyClient,
        api_key: Optional[str] = None,
        max_retries: int = 3,
        table_name: str = "image_prompt_inference",
        do_not_generate_terms: Optional[List[str]] = None,
        source_language: str = "Chinese (Simplified)",
    ):
        self.db_client = db_client
        self.table_name = table_name
        self.field_name = "word"
        self.max_retries = max_retries
        self.source_language = source_language

        settings = get_settings()
        configured_prompt_model = getattr(settings, "llm_image_prompt_model", None)
        self.model_name = _resolve_model_name(
            configured_prompt_model or settings.llm_model or DEFAULT_IMAGE_PROMPT_MODEL
        )
        self.location = settings.gcp_location
        self.project_id = settings.gcp_project_id
        self.credentials_path = (
            settings.vertex_credentials_path or settings.bq_credentials_path
        )
        self.api_token = _normalize_token(api_key or settings.resolve_llm_api_token())
        configured_template = getattr(settings, "llm_image_master_prompt_template", None)
        self.master_prompt_template = (
            str(configured_template).strip()
            if configured_template and str(configured_template).strip()
            else MASTER_IMAGE_PROMPT_TEMPLATE
        )

        configured_terms = (
            do_not_generate_terms
            if do_not_generate_terms is not None
            else getattr(settings, "llm_image_do_not_generate_terms", None)
        )
        raw_terms = configured_terms or DEFAULT_IMAGE_DO_NOT_GENERATE_TERMS
        self.blocked_terms = {
            _normalize_blocked_term(term)
            for term in raw_terms
            if _normalize_blocked_term(term)
        }

        try:
            self.client = self._build_genai_client()
        except Exception as exc:
            logger.error(f"Failed to initialize Gemini image prompt client: {exc}")
            raise ValidationError(
                "Gemini credentials are required for image prompt generation. "
                "Set LLM_API_TOKEN (or GEMINI_API_KEY / GOOGLE_API_KEY), "
                "or configure Vertex credentials."
            ) from exc

    @property
    def column_name(self) -> str:
        return "master_image_prompt"

    def _resolve_vertex_credentials(self) -> tuple[object, str]:
        return _resolve_vertex_credentials_shared(
            GenAIClientConfig(
                api_token=self.api_token,
                project_id=self.project_id,
                location=self.location,
                credentials_path=self.credentials_path,
            )
        )

    def _build_genai_client(self):
        return _build_genai_client_shared(
            GenAIClientConfig(
                api_token=self.api_token,
                project_id=self.project_id,
                location=self.location,
                credentials_path=self.credentials_path,
            )
        )

    def _extract_response_text(self, response: object) -> str:
        text = getattr(response, "text", None)
        if isinstance(text, str) and text.strip():
            return text

        try:
            candidates = getattr(response, "candidates", [])
            for candidate in candidates:
                content = getattr(candidate, "content", None)
                parts = getattr(content, "parts", None) if content else None
                if not parts:
                    continue
                part_text = getattr(parts[0], "text", None)
                if isinstance(part_text, str) and part_text.strip():
                    return part_text
        except Exception:
            pass

        return str(response)

    def _extract_json_payload(self, text: str) -> Dict[str, Any]:
        raw = text.strip()
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass

        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            snippet = raw[start : end + 1]
            payload = json.loads(snippet)
            if isinstance(payload, dict):
                return payload

        raise ValueError(f"Model response is not valid JSON object: {raw[:200]}")

    def _generate_structured_output(
        self, prompt: str, response_model: Type[BaseModel]
    ) -> BaseModel:
        generation_config = genai_types.GenerateContentConfig(
            temperature=0.1,
            response_mime_type="application/json",
        )
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=generation_config,
        )

        parsed = getattr(response, "parsed", None)
        if parsed is not None:
            if isinstance(parsed, response_model):
                return parsed
            return response_model.model_validate(parsed)

        text = self._extract_response_text(response)
        payload = self._extract_json_payload(text)
        return response_model.model_validate(payload)

    def _build_cache_key_word(self, word: str) -> str:
        blocked_terms_scope = ",".join(sorted(self.blocked_terms))
        normalized_source_language = _normalize_language_name(self.source_language)
        cache_scope = "|".join(
            [
                self.model_name,
                self.master_prompt_template,
                blocked_terms_scope,
                normalized_source_language,
            ]
        )
        cache_hash = hashlib.sha256(cache_scope.encode("utf-8")).hexdigest()[:12]
        return f"{cache_hash}::{word}"

    def _build_visual_prompt(self, word: str) -> str:
        normalized_source_language = _normalize_language_name(self.source_language)
        russian_context_hint = ""
        if normalized_source_language in {"russian", "ru"}:
            russian_context_hint = (
                "- For Russian words, keep the same Victorian gaslamp aesthetic and "
                "when relevant evoke Saint Petersburg canals, wrought-iron bridges, "
                "cobblestone embankments, and White Nights atmosphere.\n"
            )

        return (
            "You are a visual translator for language-learning flashcard image prompts.\n"
            "Return ONLY a JSON object with keys: image_term_type, visual_description.\n"
            "Allowed image_term_type values: concrete_noun, verb_action, abstract_grammar, proper_noun.\n"
            "Rules:\n"
            "- concrete_noun: richly detailed Victorian/steampunk object depiction.\n"
            "- verb_action: dynamic close-up action, avoid full faces.\n"
            "- abstract_grammar: create a physical metaphor using gaslamp fantasy aesthetics.\n"
            "- proper_noun: moody atmospheric portrait or location depiction.\n"
            f"{russian_context_hint}"
            "The visual_description must be concise but evocative English.\n"
            "Never include written text, letters, symbols, labels, signage, or speech bubbles in the scene.\n"
            "Input vocabulary word:\n"
            f"{word}"
        )

    def _format_master_prompt(self, visual_description: str) -> str:
        clean_description = (visual_description or "").strip()
        if "{visual_description}" not in self.master_prompt_template:
            return f"{self.master_prompt_template.strip()}\n\n{clean_description}".strip()
        return self.master_prompt_template.format(visual_description=clean_description)

    def _build_skipped_result(self, word: str, reason: str) -> Dict[str, Optional[str]]:
        return {
            "word": word,
            "image_term_type": None,
            "visual_description": None,
            "master_image_prompt": None,
            "image_generation_skip_reason": reason,
        }

    def process_word(self, word: str) -> Optional[Dict[str, Optional[str]]]:
        if not word or not str(word).strip():
            logger.warning("Skipping empty word in LLM image prompt transformation.")
            return None

        safe_word = str(word).strip()
        if _normalize_blocked_term(safe_word) in self.blocked_terms:
            logger.info(
                f"Skipping image prompt generation for blocked term '{safe_word}'."
            )
            result = self._build_skipped_result(
                safe_word, reason="blocked_by_do_not_generate_list"
            )
            cache_record = {**result, "word": self._build_cache_key_word(safe_word), "source_word": safe_word}
            self.db_client.insert_record(
                record=cache_record,
                columns=[col for col in cache_record.keys() if col != "word"],
                table_name=self.table_name,
                field_name=self.field_name,
            )
            return result

        cache_key_word = self._build_cache_key_word(safe_word)
        try:
            existing_record = self.db_client.find_record(
                key=cache_key_word,
                table_name=self.table_name,
                field_name=self.field_name,
            )
            if existing_record and (
                existing_record.get("master_image_prompt")
                or existing_record.get("image_generation_skip_reason")
            ):
                logger.debug(
                    f"Skipping stage-1 generation for '{safe_word}': found cached prompt."
                )
                return {
                    "word": safe_word,
                    "image_term_type": existing_record.get("image_term_type"),
                    "visual_description": existing_record.get("visual_description"),
                    "master_image_prompt": existing_record.get("master_image_prompt"),
                    "image_generation_skip_reason": existing_record.get(
                        "image_generation_skip_reason"
                    ),
                }
        except Exception as exc:
            logger.error(f"Error checking image prompt cache for word '{safe_word}': {exc}")

        try:
            @retry(
                stop=stop_after_attempt(self.max_retries),
                wait=wait_exponential(multiplier=1, min=2, max=10),
                reraise=True,
            )
            def get_visual_payload() -> VisualPromptPayload:
                result = self._generate_structured_output(
                    self._build_visual_prompt(safe_word),
                    VisualPromptPayload,
                )
                return VisualPromptPayload.model_validate(result)

            payload = get_visual_payload()
            image_term_type = _normalize_image_term_type(payload.image_term_type)
            visual_description = (payload.visual_description or "").strip()
            master_image_prompt = self._format_master_prompt(visual_description)

            result = {
                "word": safe_word,
                "image_term_type": image_term_type,
                "visual_description": visual_description,
                "master_image_prompt": master_image_prompt,
                "image_generation_skip_reason": None,
            }
            cache_record = {
                **result,
                "word": cache_key_word,
                "source_word": safe_word,
            }
            self.db_client.insert_record(
                record=cache_record,
                columns=[col for col in cache_record.keys() if col != "word"],
                table_name=self.table_name,
                field_name=self.field_name,
            )
            logger.debug(f"Image prompt data for '{safe_word}' processed and saved.")
            return result

        except Exception as exc:
            logger.error(
                f"Failed to process word '{safe_word}' for image prompt generation: {exc}"
            )
            return None

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        logger.info("Applying LLM image prompt transformation...")
        if "word" not in df.columns:
            logger.error(
                "LLMImagePromptTransformation: DataFrame must have a 'word' column."
            )
            return df

        unique_words = []
        seen = set()
        for word in df["word"]:
            safe_word = str(word or "").strip()
            if not safe_word or safe_word in seen:
                continue
            seen.add(safe_word)
            unique_words.append(safe_word)

        if not unique_words:
            logger.warning(
                "LLMImagePromptTransformation: No valid words found to process."
            )
            return df

        results = []
        for word in tqdm(unique_words, desc="LLM Image Prompt Processing"):
            result = self.process_word(word)
            if result is not None:
                results.append(result)

        if not results:
            logger.warning("LLMImagePromptTransformation: No prompts were generated.")
            return df

        df_results = pd.DataFrame(results).drop_duplicates(subset=["word"])
        merge_columns = [
            "word",
            "image_term_type",
            "visual_description",
            "master_image_prompt",
            "image_generation_skip_reason",
        ]
        generated_columns = [col for col in merge_columns if col in df_results.columns]
        if "word" not in generated_columns or len(generated_columns) <= 1:
            logger.warning(
                "LLMImagePromptTransformation: No usable image prompt columns in results."
            )
            return df

        df = pd.merge(
            df,
            df_results[generated_columns],
            on="word",
            how="left",
            suffixes=("", "_image_prompt"),
        )
        df = df.drop_duplicates(subset=["word"]).reset_index(drop=True)
        logger.info("LLM image prompt transformation applied successfully.")
        return df
