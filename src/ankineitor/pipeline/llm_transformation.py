import json
import hashlib
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, Optional, Type

import google.auth as google_auth
import pandas as pd
from dotenv import load_dotenv
from google import genai
from google.genai import types as genai_types
from google.oauth2 import credentials as oauth_credentials
from google.oauth2 import service_account
from loguru import logger
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential
from tqdm import tqdm

from .db_client import SQLAlchemyClient
from .transformations import Transformation
from ..config import get_settings
from ..security.exceptions import ValidationError

load_dotenv()


class ExampleSentences(BaseModel):
    """Structured model for example sentences."""

    sentence_1: str = Field(description="The first example sentence.")
    sentence_2: str = Field(description="The second example sentence.")
    sentence_3: str = Field(description="The third example sentence.")


class WordMeaning(BaseModel):
    """Structured model for word meanings."""

    english: str = Field(description="The meaning of the word in English.")
    spanish: str = Field(
        default="",
        description="Secondary meaning value. For Chinese this is Spanish.",
    )


def _normalize_token(raw_token: Optional[str]) -> Optional[str]:
    if raw_token is None:
        return None
    token = raw_token.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    return token or None


def _looks_like_oauth_access_token(token: str) -> bool:
    return token.startswith("ya29.")


def _looks_like_vertex_api_key(token: str) -> bool:
    return token.startswith("AQ.")


def _resolve_token_auth_mode(raw_token: Optional[str]) -> Optional[str]:
    token = _normalize_token(raw_token)
    if not token:
        return None
    if _looks_like_oauth_access_token(token):
        return "vertex_oauth_token"
    if _looks_like_vertex_api_key(token):
        return "vertex_api_key"
    return "gemini_api_key"


def _resolve_model_name(model_name: str) -> str:
    cleaned = (model_name or "").strip()
    for prefix in ("vertex_ai/", "vertexai/"):
        if cleaned.startswith(prefix):
            return cleaned[len(prefix) :]
    return cleaned or "gemini-3-flash-preview"


_CHINESE_CHAR_PATTERN = re.compile(r"[\u4e00-\u9fff]")


def _contains_chinese_characters(text: str) -> bool:
    return bool(_CHINESE_CHAR_PATTERN.search(text))


def _normalize_language_name(language: Optional[str]) -> str:
    if not language:
        return ""
    normalized = unicodedata.normalize("NFKD", language)
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower().strip()
    for token in ("_", "-", " "):
        normalized = normalized.replace(token, "")
    return normalized


def _language_is_english(language: Optional[str]) -> bool:
    normalized = _normalize_language_name(language)
    return normalized in {"en", "eng", "english"}


def _language_is_spanish(language: Optional[str]) -> bool:
    normalized = _normalize_language_name(language)
    return normalized in {"es", "spa", "spanish", "espanol"}


class LLMTransformation(Transformation):
    """
    Processes words using Gemini and caches results in a separate database.
    """

    def __init__(
        self,
        db_client: SQLAlchemyClient,
        api_key: Optional[str] = None,
        max_retries: int = 3,
        table_name: str = "llm_inference",
    ):
        self.db_client = db_client
        self.table_name = table_name
        self.field_name = "word"
        self.max_retries = max_retries

        settings = get_settings()
        self.model_name = _resolve_model_name(settings.llm_model)
        self.source_language = (
            (settings.llm_source_language or "auto").strip() or "auto"
        )
        self.target_language = (
            (settings.llm_target_language or "english").strip() or "english"
        )
        secondary_target = settings.llm_secondary_target_language
        self.secondary_target_language = (
            secondary_target.strip() if secondary_target and secondary_target.strip() else None
        )
        self.location = settings.gcp_location
        self.project_id = settings.gcp_project_id
        self.credentials_path = settings.vertex_credentials_path or settings.bq_credentials_path
        self.api_token = _normalize_token(api_key or settings.resolve_llm_api_token())
        # Backward compatible attribute name used in tests/callers.
        self.api_key = self.api_token

        try:
            self.client = self._build_genai_client()
        except Exception as exc:
            logger.error(f"Failed to initialize Gemini client: {exc}")
            raise ValidationError(
                "Gemini credentials are required. Set LLM_API_TOKEN (or GEMINI_API_KEY / GOOGLE_API_KEY), "
                "or configure Vertex credentials."
            ) from exc

    @property
    def column_name(self) -> str:
        return "meaning_english"

    def _resolve_vertex_credentials(self) -> tuple[object, str]:
        if self.credentials_path:
            path = Path(self.credentials_path)
            if path.exists():
                credentials = service_account.Credentials.from_service_account_file(
                    str(path),
                    scopes=["https://www.googleapis.com/auth/cloud-platform"],
                )
                project_id = self.project_id or credentials.project_id
                if not project_id:
                    raise ValidationError(
                        "Vertex project ID is required when using service account credentials."
                    )
                return credentials, project_id

        try:
            credentials, detected_project_id = google_auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
        except Exception as exc:
            raise ValidationError(
                "Vertex credentials not found. Set BQ_CREDENTIALS_PATH/VERTEX_CREDENTIALS_PATH "
                "or provide LLM_API_TOKEN."
            ) from exc

        project_id = self.project_id or detected_project_id
        if not project_id:
            raise ValidationError(
                "Vertex project ID is required when using ADC credentials."
            )
        return credentials, project_id

    def _build_genai_client(self) -> genai.Client:
        if self.api_token:
            mode = _resolve_token_auth_mode(self.api_token)

            if mode == "vertex_oauth_token":
                project_id = self.project_id
                if not project_id:
                    raise ValidationError(
                        "GCP_PROJECT_ID is required when using OAuth access tokens for Vertex."
                    )
                credentials = oauth_credentials.Credentials(
                    token=self.api_token,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"],
                )
                return genai.Client(
                    vertexai=True,
                    credentials=credentials,
                    project=project_id,
                    location=self.location,
                )

            if mode == "vertex_api_key":
                return genai.Client(vertexai=True, api_key=self.api_token)

            return genai.Client(api_key=self.api_token)

        credentials, project_id = self._resolve_vertex_credentials()
        return genai.Client(
            vertexai=True,
            credentials=credentials,
            project=project_id,
            location=self.location,
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

    def _resolve_language_profile(self, word: str) -> Dict[str, Optional[str]]:
        if _contains_chinese_characters(word):
            # Chinese is always fixed to EN + ES per product requirement.
            return {
                "is_chinese": True,
                "source_language": "Simplified Chinese",
                "sentence_language": "Simplified Chinese",
                "primary_target_language": "English",
                "secondary_target_language": "Spanish",
                "profile_name": "zh_fixed",
            }

        source_language = self.source_language
        sentence_language = (
            "the same language as the input word"
            if _normalize_language_name(source_language) in {"", "auto"}
            else source_language
        )
        return {
            "is_chinese": False,
            "source_language": source_language,
            "sentence_language": sentence_language,
            "primary_target_language": self.target_language,
            "secondary_target_language": self.secondary_target_language,
            "profile_name": "generic",
        }

    def _build_cache_key_word(self, word: str, profile: Dict[str, Optional[str]]) -> str:
        cache_scope = "|".join(
            [
                self.model_name,
                profile.get("profile_name") or "generic",
                profile.get("source_language") or "",
                profile.get("sentence_language") or "",
                profile.get("primary_target_language") or "",
                profile.get("secondary_target_language") or "",
            ]
        )
        cache_hash = hashlib.sha256(cache_scope.encode("utf-8")).hexdigest()[:12]
        return f"{cache_hash}::{word}"

    def _build_sentence_prompt(self, word: str, profile: Dict[str, Optional[str]]) -> str:
        sentence_language = profile.get("sentence_language") or "the same language as the input word"
        return (
            "Return a JSON object with keys sentence_1, sentence_2, sentence_3.\n"
            f"Generate 3 concise example sentences using the word '{word}'.\n"
            f"Use only {sentence_language} in the sentence values.\n"
            "Do not include translations, romanization, or explanations in the values."
        )

    def _build_meaning_prompt(self, word: str, profile: Dict[str, Optional[str]]) -> str:
        primary_target = profile.get("primary_target_language") or "English"
        secondary_target = profile.get("secondary_target_language")

        if secondary_target:
            return (
                "Return a JSON object with keys english and spanish.\n"
                f"Provide a concise meaning for the word '{word}' in {primary_target} and {secondary_target}.\n"
                f"Put the {primary_target} meaning in key 'english'.\n"
                f"Put the {secondary_target} meaning in key 'spanish'."
            )

        return (
            "Return a JSON object with keys english and spanish.\n"
            f"Provide a concise meaning for the word '{word}' in {primary_target}.\n"
            f"Put the {primary_target} meaning in key 'english'.\n"
            "Set key 'spanish' to an empty string."
        )

    def _map_meanings(
        self, profile: Dict[str, Optional[str]], meaning_obj: WordMeaning
    ) -> Dict[str, Optional[str]]:
        primary_meaning = (meaning_obj.english or "").strip()
        secondary_meaning = (meaning_obj.spanish or "").strip() or None

        # Chinese flow remains EN + ES exactly as before.
        if profile.get("is_chinese"):
            return {
                "meaning_english": primary_meaning or None,
                "meaning_spanish": secondary_meaning,
            }

        primary_target = profile.get("primary_target_language")
        secondary_target = profile.get("secondary_target_language")

        meaning_english = None
        meaning_spanish = None

        if _language_is_english(primary_target):
            meaning_english = primary_meaning or None
        if _language_is_spanish(primary_target):
            meaning_spanish = primary_meaning or None

        if _language_is_english(secondary_target) and secondary_meaning:
            meaning_english = secondary_meaning
        if _language_is_spanish(secondary_target) and secondary_meaning:
            meaning_spanish = secondary_meaning

        # Backward-compatible fallback: keep primary output in meaning_english.
        if not meaning_english and primary_meaning:
            meaning_english = primary_meaning
        if not meaning_spanish and secondary_meaning:
            meaning_spanish = secondary_meaning

        return {
            "meaning_english": meaning_english,
            "meaning_spanish": meaning_spanish,
        }

    def process_word(self, word: str) -> Optional[Dict[str, str]]:
        if not word or not word.strip():
            logger.warning("Skipping empty word in LLM transformation.")
            return None

        safe_word = word.strip()
        profile = self._resolve_language_profile(safe_word)
        cache_key_word = self._build_cache_key_word(safe_word, profile)
        logger.debug(
            "LLM processing word: {word} (source={source}, targets={primary}/{secondary})".format(
                word=safe_word,
                source=profile.get("source_language"),
                primary=profile.get("primary_target_language"),
                secondary=profile.get("secondary_target_language") or "-",
            )
        )

        try:
            existing_record = self.db_client.find_record(
                key=cache_key_word,
                table_name=self.table_name,
                field_name=self.field_name,
            )
            if (
                existing_record
                and existing_record.get("sentence_1")
                and existing_record.get("meaning_english")
            ):
                logger.debug(f"Skipping LLM for '{safe_word}': found complete data in cache.")
                return {
                    "word": safe_word,
                    "sentence_1": existing_record.get("sentence_1"),
                    "sentence_2": existing_record.get("sentence_2"),
                    "sentence_3": existing_record.get("sentence_3"),
                    "meaning_english": existing_record.get("meaning_english"),
                    "meaning_spanish": existing_record.get("meaning_spanish"),
                }
        except Exception as exc:
            logger.error(f"Error checking LLM cache for word '{safe_word}': {exc}")

        try:
            @retry(
                stop=stop_after_attempt(self.max_retries),
                wait=wait_exponential(multiplier=1, min=2, max=10),
                reraise=True,
            )
            def get_sentences() -> ExampleSentences:
                result = self._generate_structured_output(
                    self._build_sentence_prompt(safe_word, profile), ExampleSentences
                )
                return ExampleSentences.model_validate(result)

            @retry(
                stop=stop_after_attempt(self.max_retries),
                wait=wait_exponential(multiplier=1, min=2, max=10),
                reraise=True,
            )
            def get_meaning() -> WordMeaning:
                result = self._generate_structured_output(
                    self._build_meaning_prompt(safe_word, profile), WordMeaning
                )
                return WordMeaning.model_validate(result)

            sentences_obj = get_sentences()
            meaning_obj = get_meaning()
            mapped_meanings = self._map_meanings(profile, meaning_obj)

            result = {
                "word": safe_word,
                **sentences_obj.model_dump(),
                **mapped_meanings,
            }
            cache_record = {**result, "word": cache_key_word}

            self.db_client.insert_record(
                record=cache_record,
                columns=list(cache_record.keys())[1:],
                table_name=self.table_name,
                field_name=self.field_name,
            )
            logger.debug(f"LLM data for '{safe_word}' processed and saved.")
            return result

        except Exception as exc:
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
        if "meaning_spanish" in df_results.columns:
            has_secondary_values = (
                df_results["meaning_spanish"]
                .fillna("")
                .astype(str)
                .str.strip()
                .ne("")
                .any()
            )
            if not has_secondary_values:
                df_results = df_results.drop(columns=["meaning_spanish"])
                logger.info(
                    "LLMTransformation: Omitting 'meaning_spanish' column because no "
                    "secondary-language values were generated."
                )

        llm_columns = [
            "sentence_1",
            "sentence_2",
            "sentence_3",
            "meaning_english",
            "meaning_spanish",
        ]
        generated_cols = [col for col in llm_columns if col in df_results.columns]
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
        df = df.drop_duplicates(subset=["word"]).reset_index(drop=True)
        logger.info("LLM transformation applied successfully.")
        return df
