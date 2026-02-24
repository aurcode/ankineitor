import json
import hashlib
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

import pandas as pd
from google.genai import types as genai_types
from loguru import logger
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential
from tqdm import tqdm

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
from .llm_profiles import (
    LOTM_SCHEMA_ID,
    SP_RUSSIAN_SCHEMA_ID,
    SP_SPANISH_SCHEMA_ID,
    get_llm_profile,
)
from .transformations import Transformation
from ..config import get_settings
from ..security.exceptions import ValidationError


class SentencePayload(BaseModel):
    """Structured sentence entry for profile-based output."""

    target_language_highlighted: str = Field(
        description="Sentence containing the highlighted target word."
    )
    tts_clean_sentence: str = Field(
        default="",
        description="TTS-friendly sentence without markup.",
    )
    target_language_cloze: str = Field(
        description="Same sentence with the target word replaced by blanks."
    )
    sentence_pinyin: str = Field(description="Full pinyin for the sentence.")
    translation_english: str = Field(description="Natural English sentence translation.")
    translation_spanish: str = Field(
        default="", description="Natural Spanish sentence translation."
    )


class LLMWordPayload(BaseModel):
    """Structured profile output for a single target word."""

    word: str
    pinyin: str
    part_of_speech: str
    character_breakdown: str
    detailed_explanation_english: str
    detailed_explanation_spanish: str = ""
    synonyms: List[str] = Field(default_factory=list)
    antonyms: List[str] = Field(default_factory=list)
    collocations: List[str] = Field(default_factory=list)
    edge_case_notes: str = ""
    sentences: List[SentencePayload] = Field(default_factory=list)


class SPRussianSentencePayload(BaseModel):
    """Structured sentence entry for SP Russian profile output."""

    target_language_highlighted: str = Field(
        description="Sentence containing the highlighted target word."
    )
    tts_clean_sentence: str = Field(
        description="TTS-friendly sentence without stress marks or markup."
    )
    target_language_cloze: str = Field(
        description="Same sentence with the target word replaced by blanks."
    )
    sentence_romanization: str = Field(
        description="Romanized sentence with stress marks."
    )
    translation_english: str = Field(description="Natural English sentence translation.")
    translation_spanish: str = Field(
        default="", description="Natural Spanish sentence translation."
    )


class SPRussianWordPayload(BaseModel):
    """Structured SP Russian profile output for a single target word."""

    word: str
    word_with_stress: str
    romanization: str
    part_of_speech: str
    aspect_pair: str = ""
    morphological_breakdown: str
    register_label: str = Field(alias="register")
    grammar_formula: str = ""
    detailed_explanation_english: str
    detailed_explanation_spanish: str
    mnemonic_hook_spanish: str
    piter_summer_variant: str
    synonyms: List[str] = Field(default_factory=list)
    antonyms: List[str] = Field(default_factory=list)
    collocations: List[str] = Field(default_factory=list)
    edge_case_notes: str = ""
    sentences: List[SPRussianSentencePayload] = Field(default_factory=list)


class SPSpanishSentencePayload(BaseModel):
    """Structured sentence entry for standard Spanish profile output."""

    target_language_highlighted: str = Field(
        description="Sentence containing the highlighted target word."
    )
    tts_clean_sentence: str = Field(
        description="TTS-friendly sentence without markup."
    )
    target_language_cloze: str = Field(
        description="Same sentence with the target word replaced by blanks."
    )
    sentence_pronunciation_hint: str = Field(
        default="",
        description="Optional pronunciation aid for edge cases.",
    )
    translation_english: str = Field(description="Natural English sentence translation.")
    translation_spanish: str = Field(
        default="",
        description="Natural Spanish paraphrase sentence.",
    )


class SPSpanishWordPayload(BaseModel):
    """Structured standard Spanish profile output for a single target word."""

    word: str
    lemma: str = ""
    pronunciation_ipa: str = ""
    syllabification_and_stress: str = ""
    part_of_speech: str
    morphological_breakdown: str
    register_label: str = Field(alias="register")
    regional_scope: str = ""
    grammar_formula: str = ""
    ser_estar_note: str = ""
    por_para_note: str = ""
    reflexive_variant: str = ""
    irregular_forms: List[str] = Field(default_factory=list)
    detailed_explanation_english: str
    detailed_explanation_spanish: str
    common_mistakes: List[str] = Field(default_factory=list)
    synonyms: List[str] = Field(default_factory=list)
    antonyms: List[str] = Field(default_factory=list)
    collocations: List[str] = Field(default_factory=list)
    edge_case_notes: str = ""
    sentences: List[SPSpanishSentencePayload] = Field(default_factory=list)


class LLMTransformation(Transformation):
    """
    Processes words using Gemini and caches results in a separate database.
    """

    pipeline_stage = "llm"

    # Legacy duplicate fields should stay internal to cache but not leak into pipeline CSV output.
    _legacy_pipeline_output_columns = {
        "synonyms_rendered",
        "antonyms_rendered",
        "collocations_rendered",
        "sentences_rendered_html",
        "example_sentences",
        "improved_meaning",
        "pinyin",
        "translation",
    }

    def __init__(
        self,
        db_client: SQLAlchemyClient,
        api_key: Optional[str] = None,
        max_retries: int = 3,
        table_name: str = "llm_inference",
        profile_id: Optional[str] = None,
    ):
        self.db_client = db_client
        self.table_name = table_name
        self.field_name = "word"
        self.max_retries = max_retries

        settings = get_settings()
        self.model_name = _resolve_model_name(settings.llm_model)
        self.profile_id = (
            profile_id
            or (getattr(settings, "llm_profile_id", None) or "").strip()
        )
        self.profile = get_llm_profile(self.profile_id)
        self.llm_cache_db_path = (
            (getattr(settings, "llm_cache_db_path", None) or "").strip()
            or "data/ankineitor_llm_cache.db"
        )
        self.profile_db_isolation_enabled = bool(
            getattr(settings, "llm_profile_db_isolation", True)
        )
        self._profile_db_clients: Dict[str, SQLAlchemyClient] = {}
        self.llm_raw_response_db_path = (
            (getattr(settings, "llm_raw_response_db_path", None) or "").strip()
            or "data/ankineitor_llm_raw_response.db"
        )
        self.raw_response_table_name = "llm_raw_response"
        self._raw_response_columns = [
            "record_id",
            "created_at",
            "cache_key_word",
            "word",
            "profile_id",
            "profile_version",
            "model_name",
            "parse_status",
            "parse_error",
            "raw_response_text",
            "extracted_payload_json",
            "normalized_payload_json",
        ]
        self._raw_response_db_client: Optional[SQLAlchemyClient] = None
        self._last_generation_debug: Dict[str, Optional[str]] = {}
        self.location = settings.gcp_location
        self.project_id = settings.gcp_project_id
        self.credentials_path = settings.vertex_credentials_path or settings.bq_credentials_path
        self.api_token = _normalize_token(api_key or settings.resolve_llm_api_token())
        # Backward compatible attribute name used in tests/callers.
        self.api_key = self.api_token

        # Cache schema columns for table `llm_inference`.
        self._cache_columns = [
            "profile_id",
            "profile_version",
            "word_model",
            "pinyin",
            "part_of_speech",
            "character_breakdown",
            "detailed_explanation_english",
            "detailed_explanation_spanish",
            "word_with_stress",
            "romanization",
            "aspect_pair",
            "register",
            "grammar_formula",
            "mnemonic_hook_spanish",
            "piter_summer_variant",
            "edge_case_notes",
            "synonyms_json",
            "antonyms_json",
            "collocations_json",
            "sentences_json",
            "synonyms_rendered",
            "antonyms_rendered",
            "collocations_rendered",
            "sentences_rendered_html",
            "example_sentences",
            "improved_meaning",
            "sentence_1",
            "sentence_2",
            "sentence_3",
            "meaning_english",
            "meaning_spanish",
        ]

        try:
            self.client = self._build_genai_client()
        except Exception as exc:
            logger.error(f"Failed to initialize Gemini client: {exc}")
            raise ValidationError(
                "Gemini credentials are required. Set LLM_API_TOKEN (or GEMINI_API_KEY / GOOGLE_API_KEY), "
                "or configure Vertex credentials."
            ) from exc
        try:
            self._raw_response_db_client = SQLAlchemyClient(
                db_path=self.llm_raw_response_db_path
            )
        except Exception as exc:
            logger.warning(
                "Failed to initialize raw LLM response DB '{}': {}",
                self.llm_raw_response_db_path,
                exc,
            )

    @property
    def column_name(self) -> str:
        return "meaning_english"

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

    def _strip_markdown_fence(self, text: str) -> str:
        stripped = (text or "").strip()
        fence_match = re.match(
            r"^\s*```(?:json|JSON)?\s*(.*?)\s*```\s*$",
            stripped,
            flags=re.DOTALL,
        )
        if fence_match:
            return fence_match.group(1).strip()
        return stripped

    def _decode_nested_json(self, value: Any, max_depth: int = 3) -> Any:
        current = value
        for _ in range(max_depth):
            if not isinstance(current, str):
                break
            candidate = self._strip_markdown_fence(current).strip()
            if not candidate:
                break
            try:
                current = json.loads(candidate)
            except json.JSONDecodeError:
                break
        return current

    def _coerce_payload_object(self, payload: Any) -> Dict[str, Any]:
        normalized = self._decode_nested_json(payload)
        if isinstance(normalized, dict):
            return normalized
        if (
            isinstance(normalized, list)
            and len(normalized) == 1
            and isinstance(normalized[0], dict)
        ):
            return normalized[0]
        raise ValueError("Model response JSON must be an object.")

    def _extract_json_payload(self, text: str) -> Dict[str, Any]:
        raw = (text or "").strip()
        if not raw:
            raise ValueError("Model response is empty.")

        # First pass: direct/recursive parse.
        try:
            return self._coerce_payload_object(raw)
        except Exception:
            pass

        # Second pass: extract fenced json block(s).
        fenced_blocks = re.findall(
            r"```(?:json|JSON)?\s*(.*?)```",
            raw,
            flags=re.DOTALL,
        )
        for block in fenced_blocks:
            try:
                return self._coerce_payload_object(block)
            except Exception:
                continue

        # Third pass: decode first JSON object/array from mixed text.
        decoder = json.JSONDecoder()
        for idx, char in enumerate(raw):
            if char not in "{[":
                continue
            try:
                payload, _ = decoder.raw_decode(raw[idx:])
            except json.JSONDecodeError:
                continue
            try:
                return self._coerce_payload_object(payload)
            except Exception:
                continue

        raise ValueError(f"Model response is not valid JSON object: {raw[:200]}")

    def _generate_structured_output(
        self, prompt: str, response_model: Type[BaseModel]
    ) -> BaseModel:
        debug_payload: Dict[str, Optional[str]] = {
            "raw_response_text": None,
            "extracted_payload_json": None,
            "normalized_payload_json": None,
            "parse_status": "failed",
            "parse_error": None,
        }
        generation_config = genai_types.GenerateContentConfig(
            temperature=0.1,
            response_mime_type="application/json",
        )
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=generation_config,
            )

            text = self._extract_response_text(response)
            debug_payload["raw_response_text"] = text

            parsed = getattr(response, "parsed", None)
            if parsed is not None:
                if isinstance(parsed, response_model):
                    model_payload = parsed
                else:
                    model_payload = response_model.model_validate(parsed)
                debug_payload["extracted_payload_json"] = json.dumps(
                    model_payload.model_dump(by_alias=True),
                    ensure_ascii=False,
                )
                debug_payload["normalized_payload_json"] = debug_payload[
                    "extracted_payload_json"
                ]
                debug_payload["parse_status"] = "parsed_field_validated"
                return model_payload

            payload = self._extract_json_payload(text)
            debug_payload["extracted_payload_json"] = json.dumps(
                payload,
                ensure_ascii=False,
            )
            model_payload = response_model.model_validate(payload)
            debug_payload["normalized_payload_json"] = json.dumps(
                model_payload.model_dump(by_alias=True),
                ensure_ascii=False,
            )
            debug_payload["parse_status"] = "text_json_validated"
            return model_payload
        except Exception as exc:
            debug_payload["parse_error"] = str(exc)
            raise
        finally:
            self._last_generation_debug = debug_payload

    def _resolve_profile(self, word: str):
        del word
        return get_llm_profile(self.profile_id)

    def _sanitize_profile_id_for_filename(self, profile_id: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9_-]+", "_", (profile_id or "").strip().lower())
        safe = safe.strip("_")
        return safe or "default"

    def _build_profile_db_path(self, profile_id: str) -> str:
        base = Path(self.llm_cache_db_path)
        safe_profile = self._sanitize_profile_id_for_filename(profile_id)
        suffix = "".join(base.suffixes) or ".db"
        stem = base.name[: -len(suffix)] if suffix and base.name.endswith(suffix) else base.stem
        filename = f"{stem}__{safe_profile}{suffix}"
        return str(base.with_name(filename))

    def _get_active_profile_db_client(self) -> SQLAlchemyClient:
        if not self.profile_db_isolation_enabled:
            return self.db_client

        # Keep test mocks and non-standard db clients backward compatible.
        if not isinstance(self.db_client, SQLAlchemyClient):
            return self.db_client

        profile_key = self.profile.profile_id
        if profile_key in self._profile_db_clients:
            return self._profile_db_clients[profile_key]

        db_path = self._build_profile_db_path(profile_key)
        client = SQLAlchemyClient(db_path=db_path)
        self._profile_db_clients[profile_key] = client
        logger.info(
            "LLMTransformation profile DB selected: profile='{}' db='{}'",
            profile_key,
            db_path,
        )
        return client

    def _build_cache_key_word(self, word: str) -> str:
        scope = "|".join(
            [
                self.model_name,
                self.profile.profile_id,
                self.profile.prompt_version,
            ]
        )
        cache_hash = hashlib.sha256(scope.encode("utf-8")).hexdigest()[:12]
        return f"{cache_hash}::{word}"

    def _build_profile_prompt(self, word: str) -> str:
        return self.profile.render_prompt(word)

    def _get_response_model_for_profile(self) -> Type[BaseModel]:
        schema = (self.profile.response_schema or "").strip()
        if schema == SP_RUSSIAN_SCHEMA_ID:
            return SPRussianWordPayload
        if schema == SP_SPANISH_SCHEMA_ID:
            return SPSpanishWordPayload
        return LLMWordPayload

    def _as_clean_list(self, items: List[str]) -> List[str]:
        cleaned: List[str] = []
        for item in items or []:
            value = str(item).strip()
            if value:
                cleaned.append(value)
        return cleaned

    def _build_translation_extras(
        self,
        detailed_en: Optional[str],
        detailed_es: Optional[str],
        part_of_speech: Optional[str],
        character_breakdown: Optional[str],
        edge_case_notes: Optional[str],
        extra_lines: Optional[List[str]] = None,
    ) -> Optional[str]:
        lines: List[str] = []
        if detailed_en:
            lines.append(f"EN: {detailed_en}")
        if detailed_es:
            lines.append(f"ES: {detailed_es}")
        if part_of_speech:
            lines.append(f"POS: {part_of_speech}")
        if character_breakdown:
            lines.append(f"Breakdown: {character_breakdown}")
        if edge_case_notes:
            lines.append(f"Notes: {edge_case_notes}")
        for line in extra_lines or []:
            value = str(line).strip()
            if value:
                lines.append(value)
        return "\n".join(lines) if lines else None

    def _build_sentences_rendered_html(self, sentences: List[Any]) -> Optional[str]:
        if not sentences:
            return None

        lines: List[str] = ["<ol>"]
        for sentence in sentences:
            highlighted = str(
                getattr(sentence, "target_language_highlighted", "") or ""
            ).strip()
            phonetic = str(
                getattr(sentence, "sentence_pinyin", None)
                or getattr(sentence, "sentence_romanization", None)
                or getattr(sentence, "sentence_pronunciation_hint", None)
                or ""
            ).strip()
            trans_en = str(getattr(sentence, "translation_english", "") or "").strip()
            trans_es = str(getattr(sentence, "translation_spanish", "") or "").strip()

            lines.append("<li>")
            lines.append(highlighted)
            if phonetic:
                lines.append(f"<br><i>{phonetic}</i>")
            if trans_en:
                lines.append(f"<br>EN: {trans_en}")
            if trans_es:
                lines.append(f"<br>ES: {trans_es}")
            lines.append("</li>")

        lines.append("</ol>")
        return "".join(lines)

    def _resolve_tts_clean_sentence(self, sentence: Any) -> Optional[str]:
        """Use explicit TTS text when provided, otherwise strip markup from highlighted."""
        explicit_tts = str(getattr(sentence, "tts_clean_sentence", "") or "").strip()
        if explicit_tts:
            return explicit_tts

        highlighted = str(getattr(sentence, "target_language_highlighted", "") or "").strip()
        if not highlighted:
            return None

        # Fallback keeps backwards compatibility with older payloads lacking tts_clean_sentence.
        cleaned = re.sub(r"<[^>]+>", "", highlighted).strip()
        return cleaned or None

    def _payload_to_result_lotm(
        self, safe_word: str, payload_obj: LLMWordPayload
    ) -> Dict[str, Optional[str]]:
        normalized_word = (payload_obj.word or "").strip() or safe_word
        pinyin_value = (payload_obj.pinyin or "").strip() or None
        part_of_speech = (payload_obj.part_of_speech or "").strip() or None
        character_breakdown = (payload_obj.character_breakdown or "").strip() or None
        detailed_en = (payload_obj.detailed_explanation_english or "").strip() or None
        detailed_es = (payload_obj.detailed_explanation_spanish or "").strip() or None
        edge_case_notes = (payload_obj.edge_case_notes or "").strip() or None

        synonyms = self._as_clean_list(payload_obj.synonyms)
        antonyms = self._as_clean_list(payload_obj.antonyms)
        collocations = self._as_clean_list(payload_obj.collocations)
        sentences = payload_obj.sentences or []

        sentences_json = json.dumps(
            [s.model_dump() for s in sentences], ensure_ascii=False
        )
        payload_json = json.dumps(payload_obj.model_dump(by_alias=True), ensure_ascii=False)

        result: Dict[str, Optional[str]] = {
            "word": safe_word,
            "word_model": normalized_word,
            "profile_id": self.profile.profile_id,
            "profile_version": self.profile.prompt_version,
            "pinyin": pinyin_value,
            "part_of_speech": part_of_speech,
            "character_breakdown": character_breakdown,
            "detailed_explanation_english": detailed_en,
            "detailed_explanation_spanish": detailed_es,
            # Keep legacy meaning columns for existing templates.
            "meaning_english": detailed_en,
            "meaning_spanish": detailed_es,
            "edge_case_notes": edge_case_notes,
            "synonyms_json": json.dumps(synonyms, ensure_ascii=False),
            "antonyms_json": json.dumps(antonyms, ensure_ascii=False),
            "collocations_json": json.dumps(collocations, ensure_ascii=False),
            "sentences_json": sentences_json,
            "synonyms_rendered": " | ".join(synonyms) if synonyms else None,
            "antonyms_rendered": " | ".join(antonyms) if antonyms else None,
            "collocations_rendered": " | ".join(collocations) if collocations else None,
            "sentences_rendered_html": self._build_sentences_rendered_html(sentences),
            "translation": self._build_translation_extras(
                detailed_en=detailed_en,
                detailed_es=detailed_es,
                part_of_speech=part_of_speech,
                character_breakdown=character_breakdown,
                edge_case_notes=edge_case_notes,
            ),
            # Existing llm cache columns.
            "example_sentences": sentences_json,
            "improved_meaning": payload_json,
        }

        for idx, sentence in enumerate(sentences, start=1):
            result[f"sentence_{idx}"] = (
                sentence.target_language_highlighted.strip() or None
            )
            result[f"sentence_{idx}_tts_clean"] = self._resolve_tts_clean_sentence(
                sentence
            )
            result[f"sentence_{idx}_cloze"] = (
                sentence.target_language_cloze.strip() or None
            )
            result[f"sentence_{idx}_pinyin"] = sentence.sentence_pinyin.strip() or None
            result[f"sentence_{idx}_translation_english"] = (
                sentence.translation_english.strip() or None
            )
            result[f"sentence_{idx}_translation_spanish"] = (
                sentence.translation_spanish.strip() or None
            )

        return result

    def _payload_to_result_sp_russian(
        self, safe_word: str, payload_obj: SPRussianWordPayload
    ) -> Dict[str, Optional[str]]:
        normalized_word = (payload_obj.word or "").strip() or safe_word
        word_with_stress = (payload_obj.word_with_stress or "").strip() or None
        romanization = (payload_obj.romanization or "").strip() or None
        part_of_speech = (payload_obj.part_of_speech or "").strip() or None
        aspect_pair = (payload_obj.aspect_pair or "").strip() or None
        morphological_breakdown = (
            (payload_obj.morphological_breakdown or "").strip() or None
        )
        register = (payload_obj.register_label or "").strip() or None
        grammar_formula = (payload_obj.grammar_formula or "").strip() or None
        detailed_en = (payload_obj.detailed_explanation_english or "").strip() or None
        detailed_es = (payload_obj.detailed_explanation_spanish or "").strip() or None
        mnemonic_hook_spanish = (payload_obj.mnemonic_hook_spanish or "").strip() or None
        piter_summer_variant = (payload_obj.piter_summer_variant or "").strip() or None
        edge_case_notes = (payload_obj.edge_case_notes or "").strip() or None

        synonyms = self._as_clean_list(payload_obj.synonyms)
        antonyms = self._as_clean_list(payload_obj.antonyms)
        collocations = self._as_clean_list(payload_obj.collocations)
        sentences = payload_obj.sentences or []

        sentences_json = json.dumps([s.model_dump() for s in sentences], ensure_ascii=False)
        payload_json = json.dumps(payload_obj.model_dump(by_alias=True), ensure_ascii=False)

        result: Dict[str, Optional[str]] = {
            "word": safe_word,
            "word_model": normalized_word,
            "profile_id": self.profile.profile_id,
            "profile_version": self.profile.prompt_version,
            "word_with_stress": word_with_stress,
            "romanization": romanization,
            # Russian profile should not emit Chinese-specific helper columns.
            "pinyin": None,
            "part_of_speech": part_of_speech,
            "character_breakdown": morphological_breakdown,
            "aspect_pair": aspect_pair,
            "register": register,
            "grammar_formula": grammar_formula,
            "detailed_explanation_english": detailed_en,
            "detailed_explanation_spanish": detailed_es,
            "meaning_english": detailed_en,
            "meaning_spanish": detailed_es,
            "mnemonic_hook_spanish": mnemonic_hook_spanish,
            "piter_summer_variant": piter_summer_variant,
            "edge_case_notes": edge_case_notes,
            "synonyms_json": json.dumps(synonyms, ensure_ascii=False),
            "antonyms_json": json.dumps(antonyms, ensure_ascii=False),
            "collocations_json": json.dumps(collocations, ensure_ascii=False),
            "sentences_json": sentences_json,
            "synonyms_rendered": " | ".join(synonyms) if synonyms else None,
            "antonyms_rendered": " | ".join(antonyms) if antonyms else None,
            "collocations_rendered": " | ".join(collocations) if collocations else None,
            "sentences_rendered_html": self._build_sentences_rendered_html(sentences),
            "translation": None,
            "example_sentences": sentences_json,
            "improved_meaning": payload_json,
        }

        for idx, sentence in enumerate(sentences, start=1):
            result[f"sentence_{idx}"] = (
                sentence.target_language_highlighted.strip() or None
            )
            result[f"sentence_{idx}_tts_clean"] = (
                sentence.tts_clean_sentence.strip() or None
            )
            result[f"sentence_{idx}_cloze"] = (
                sentence.target_language_cloze.strip() or None
            )
            result[f"sentence_{idx}_romanization"] = (
                sentence.sentence_romanization.strip() or None
            )
            result[f"sentence_{idx}_translation_english"] = (
                sentence.translation_english.strip() or None
            )
            result[f"sentence_{idx}_translation_spanish"] = (
                sentence.translation_spanish.strip() or None
            )

        return result

    def _payload_to_result_sp_spanish(
        self, safe_word: str, payload_obj: SPSpanishWordPayload
    ) -> Dict[str, Optional[str]]:
        normalized_word = (payload_obj.word or "").strip() or safe_word
        lemma = (payload_obj.lemma or "").strip() or normalized_word
        pronunciation_ipa = (payload_obj.pronunciation_ipa or "").strip() or None
        syllabification_and_stress = (
            (payload_obj.syllabification_and_stress or "").strip() or None
        )
        part_of_speech = (payload_obj.part_of_speech or "").strip() or None
        morphological_breakdown = (
            (payload_obj.morphological_breakdown or "").strip() or None
        )
        register = (payload_obj.register_label or "").strip() or None
        regional_scope = (payload_obj.regional_scope or "").strip() or None
        grammar_formula = (payload_obj.grammar_formula or "").strip() or None
        ser_estar_note = (payload_obj.ser_estar_note or "").strip() or None
        por_para_note = (payload_obj.por_para_note or "").strip() or None
        reflexive_variant = (payload_obj.reflexive_variant or "").strip() or None
        detailed_en = (payload_obj.detailed_explanation_english or "").strip() or None
        detailed_es = (payload_obj.detailed_explanation_spanish or "").strip() or None
        edge_case_notes = (payload_obj.edge_case_notes or "").strip() or None

        irregular_forms = self._as_clean_list(payload_obj.irregular_forms)
        common_mistakes = self._as_clean_list(payload_obj.common_mistakes)
        synonyms = self._as_clean_list(payload_obj.synonyms)
        antonyms = self._as_clean_list(payload_obj.antonyms)
        collocations = self._as_clean_list(payload_obj.collocations)
        sentences = payload_obj.sentences or []

        sentences_json = json.dumps([s.model_dump() for s in sentences], ensure_ascii=False)
        payload_json = json.dumps(payload_obj.model_dump(by_alias=True), ensure_ascii=False)

        result: Dict[str, Optional[str]] = {
            "word": safe_word,
            "word_model": lemma,
            "profile_id": self.profile.profile_id,
            "profile_version": self.profile.prompt_version,
            "lemma": lemma,
            "pronunciation_ipa": pronunciation_ipa,
            "syllabification_and_stress": syllabification_and_stress,
            "regional_scope": regional_scope,
            "ser_estar_note": ser_estar_note,
            "por_para_note": por_para_note,
            "reflexive_variant": reflexive_variant,
            "irregular_forms_json": json.dumps(irregular_forms, ensure_ascii=False),
            "common_mistakes_json": json.dumps(common_mistakes, ensure_ascii=False),
            "word_with_stress": None,
            "romanization": pronunciation_ipa,
            "pinyin": None,
            "part_of_speech": part_of_speech,
            "character_breakdown": morphological_breakdown,
            "aspect_pair": reflexive_variant,
            "register": register,
            "grammar_formula": grammar_formula,
            "detailed_explanation_english": detailed_en,
            "detailed_explanation_spanish": detailed_es,
            "meaning_english": detailed_en,
            "meaning_spanish": detailed_es,
            "mnemonic_hook_spanish": None,
            "piter_summer_variant": None,
            "edge_case_notes": edge_case_notes,
            "synonyms_json": json.dumps(synonyms, ensure_ascii=False),
            "antonyms_json": json.dumps(antonyms, ensure_ascii=False),
            "collocations_json": json.dumps(collocations, ensure_ascii=False),
            "sentences_json": sentences_json,
            "synonyms_rendered": " | ".join(synonyms) if synonyms else None,
            "antonyms_rendered": " | ".join(antonyms) if antonyms else None,
            "collocations_rendered": " | ".join(collocations) if collocations else None,
            "sentences_rendered_html": self._build_sentences_rendered_html(sentences),
            "translation": None,
            "example_sentences": sentences_json,
            "improved_meaning": payload_json,
        }

        for idx, sentence in enumerate(sentences, start=1):
            result[f"sentence_{idx}"] = (
                sentence.target_language_highlighted.strip() or None
            )
            result[f"sentence_{idx}_tts_clean"] = (
                sentence.tts_clean_sentence.strip() or None
            )
            result[f"sentence_{idx}_cloze"] = (
                sentence.target_language_cloze.strip() or None
            )
            result[f"sentence_{idx}_pronunciation_hint"] = (
                sentence.sentence_pronunciation_hint.strip() or None
            )
            result[f"sentence_{idx}_translation_english"] = (
                sentence.translation_english.strip() or None
            )
            result[f"sentence_{idx}_translation_spanish"] = (
                sentence.translation_spanish.strip() or None
            )

        return result

    def _payload_to_result(
        self,
        safe_word: str,
        payload_obj: BaseModel,
    ) -> Dict[str, Optional[str]]:
        if isinstance(payload_obj, SPRussianWordPayload):
            return self._payload_to_result_sp_russian(safe_word, payload_obj)
        if isinstance(payload_obj, SPSpanishWordPayload):
            return self._payload_to_result_sp_spanish(safe_word, payload_obj)
        return self._payload_to_result_lotm(
            safe_word, LLMWordPayload.model_validate(payload_obj)
        )

    def _cache_record_from_result(
        self,
        cache_key_word: str,
        result: Dict[str, Optional[str]],
    ) -> Dict[str, Optional[str]]:
        return {
            "word": cache_key_word,
            "profile_id": result.get("profile_id"),
            "profile_version": result.get("profile_version"),
            "word_model": result.get("word_model"),
            "pinyin": result.get("pinyin"),
            "part_of_speech": result.get("part_of_speech"),
            "character_breakdown": result.get("character_breakdown"),
            "detailed_explanation_english": result.get("detailed_explanation_english"),
            "detailed_explanation_spanish": result.get("detailed_explanation_spanish"),
            "word_with_stress": result.get("word_with_stress"),
            "romanization": result.get("romanization"),
            "aspect_pair": result.get("aspect_pair"),
            "register": result.get("register"),
            "grammar_formula": result.get("grammar_formula"),
            "mnemonic_hook_spanish": result.get("mnemonic_hook_spanish"),
            "piter_summer_variant": result.get("piter_summer_variant"),
            "edge_case_notes": result.get("edge_case_notes"),
            "synonyms_json": result.get("synonyms_json"),
            "antonyms_json": result.get("antonyms_json"),
            "collocations_json": result.get("collocations_json"),
            "sentences_json": result.get("sentences_json"),
            "synonyms_rendered": result.get("synonyms_rendered"),
            "antonyms_rendered": result.get("antonyms_rendered"),
            "collocations_rendered": result.get("collocations_rendered"),
            "sentences_rendered_html": result.get("sentences_rendered_html"),
            "example_sentences": result.get("example_sentences"),
            "improved_meaning": result.get("improved_meaning"),
            "sentence_1": result.get("sentence_1"),
            "sentence_2": result.get("sentence_2"),
            "sentence_3": result.get("sentence_3"),
            "meaning_english": result.get("meaning_english"),
            "meaning_spanish": result.get("meaning_spanish"),
        }

    def _result_from_cached_record(
        self,
        safe_word: str,
        existing_record: Dict[str, Any],
    ) -> Optional[Dict[str, Optional[str]]]:
        payload_json = existing_record.get("improved_meaning")
        if isinstance(payload_json, str) and payload_json.strip().startswith("{"):
            response_model = self._get_response_model_for_profile()
            try:
                payload = response_model.model_validate(json.loads(payload_json))
                result = self._payload_to_result(safe_word, payload)
                result["word"] = safe_word
                return result
            except Exception as exc:
                logger.debug(
                    f"Failed to hydrate profile payload for '{safe_word}' from cache: {exc}"
                )

        # Fallback for legacy cache rows.
        if existing_record.get("sentence_1") and existing_record.get("meaning_english"):
            return {
                "word": safe_word,
                "sentence_1": existing_record.get("sentence_1"),
                "sentence_2": existing_record.get("sentence_2"),
                "sentence_3": existing_record.get("sentence_3"),
                "meaning_english": existing_record.get("meaning_english"),
                "meaning_spanish": existing_record.get("meaning_spanish"),
                "example_sentences": existing_record.get("example_sentences"),
                "improved_meaning": existing_record.get("improved_meaning"),
            }
        return None

    def _strip_legacy_output_columns(
        self, result: Optional[Dict[str, Optional[str]]]
    ) -> Optional[Dict[str, Optional[str]]]:
        if result is None:
            return None
        return {
            key: value
            for key, value in result.items()
            if key not in self._legacy_pipeline_output_columns
        }

    def _persist_raw_response_snapshot(self, cache_key_word: str, safe_word: str) -> None:
        if self._raw_response_db_client is None:
            return

        snapshot = dict(self._last_generation_debug or {})
        if not snapshot:
            return

        record = {
            "record_id": uuid.uuid4().hex,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "cache_key_word": cache_key_word,
            "word": safe_word,
            "profile_id": self.profile.profile_id,
            "profile_version": self.profile.prompt_version,
            "model_name": self.model_name,
            "parse_status": snapshot.get("parse_status"),
            "parse_error": snapshot.get("parse_error"),
            "raw_response_text": snapshot.get("raw_response_text"),
            "extracted_payload_json": snapshot.get("extracted_payload_json"),
            "normalized_payload_json": snapshot.get("normalized_payload_json"),
        }
        try:
            self._raw_response_db_client.insert_record(
                record=record,
                columns=self._raw_response_columns,
                table_name=self.raw_response_table_name,
                field_name="record_id",
            )
        except Exception as exc:
            logger.debug(
                "Failed to persist raw LLM response for '{}' to '{}': {}",
                safe_word,
                self.llm_raw_response_db_path,
                exc,
            )

    def process_word(self, word: str) -> Optional[Dict[str, Optional[str]]]:
        if not word or not word.strip():
            logger.warning("Skipping empty word in LLM transformation.")
            return None

        safe_word = word.strip()
        self.profile = self._resolve_profile(safe_word)
        db_client = self._get_active_profile_db_client()
        cache_key_word = self._build_cache_key_word(safe_word)
        logger.debug(
            "LLM processing word: {word} (profile={profile})".format(
                word=safe_word,
                profile=self.profile.display_name,
            )
        )

        try:
            existing_record = db_client.find_record(
                key=cache_key_word,
                table_name=self.table_name,
                field_name=self.field_name,
            )
            if existing_record:
                cached_result = self._result_from_cached_record(safe_word, existing_record)
                if cached_result is not None:
                    logger.debug(
                        f"Skipping LLM for '{safe_word}': found profile data in cache."
                    )
                    return self._strip_legacy_output_columns(cached_result)
        except Exception as exc:
            logger.error(f"Error checking LLM cache for word '{safe_word}': {exc}")

        try:
            self._last_generation_debug = {}
            response_model = self._get_response_model_for_profile()

            @retry(
                stop=stop_after_attempt(self.max_retries),
                wait=wait_exponential(multiplier=1, min=2, max=10),
                reraise=True,
            )
            def get_payload() -> BaseModel:
                result = self._generate_structured_output(
                    self._build_profile_prompt(safe_word), response_model
                )
                return response_model.model_validate(result)

            payload_obj = get_payload()
            result = self._payload_to_result(safe_word, payload_obj)
            cache_record = self._cache_record_from_result(cache_key_word, result)

            db_client.insert_record(
                record=cache_record,
                columns=self._cache_columns,
                table_name=self.table_name,
                field_name=self.field_name,
            )
            self._persist_raw_response_snapshot(cache_key_word, safe_word)
            logger.debug(f"LLM data for '{safe_word}' processed and saved.")
            return self._strip_legacy_output_columns(result)

        except Exception as exc:
            self._persist_raw_response_snapshot(cache_key_word, safe_word)
            logger.error(f"Failed to process word '{safe_word}' with Gemini after retries: {exc}")
            return None

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        logger.info("Applying LLM transformation...")
        if "word" not in df.columns:
            logger.error("LLMTransformation: DataFrame must have a 'word' column.")
            return df

        results = []
        for word in tqdm(df["word"], desc="LLM Processing"):
            if not word or not str(word).strip():
                logger.warning("Skipping empty word.")
                results.append(None)
                continue
            results.append(self.process_word(str(word)))

        valid_results = [r for r in results if r is not None]
        if not valid_results:
            logger.warning("LLMTransformation: No words were processed successfully.")
            return df

        df_results = pd.DataFrame(valid_results)
        generated_cols = [col for col in df_results.columns if col != "word"]
        if not generated_cols:
            logger.warning("LLMTransformation: No LLM columns in results.")
            return df

        final_llm_cols = ["word"] + generated_cols
        df = pd.merge(
            df,
            df_results[final_llm_cols],
            on="word",
            how="left",
            suffixes=("", "_llm"),
        )
        if self.profile.response_schema in {SP_RUSSIAN_SCHEMA_ID, SP_SPANISH_SCHEMA_ID}:
            # Keep non-Chinese output focused: no pinyin/translation columns.
            for col in ("pinyin", "translation"):
                if col in df.columns:
                    df[col] = None
            for col in ("pinyin_llm", "translation_llm"):
                if col in df.columns:
                    df = df.drop(columns=[col])
        df = df.drop_duplicates(subset=["word"]).reset_index(drop=True)
        logger.info("LLM transformation applied successfully.")
        return df
