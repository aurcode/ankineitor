import hashlib
import mimetypes
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from google.genai import types as genai_types
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential
from tqdm import tqdm

from ..config import get_settings
from ..security.exceptions import ValidationError
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
    DEFAULT_LLM_PROFILE_ID,
    SP_SPANISH_STANDARD_PROFILE_ID,
)
from .transformations import Transformation

DEFAULT_IMAGE_MODEL = "gemini-3-pro-image-preview"
FALLBACK_IMAGE_OUTPUT_DIR = "/tmp/ankineitor_image_files"
IMAGE_PROMPT_COLUMN = "master_image_prompt"
IMAGE_SKIP_REASON_COLUMN = "image_generation_skip_reason"
IMAGE_RENDER_STATUS_COLUMN = "image_render_status"
IMAGE_RENDER_SKIP_REASON_COLUMN = "image_render_skip_reason"


def _directory_is_writable(directory: Path) -> bool:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe_path = directory / ".ankineitor_write_probe"
        probe_path.write_bytes(b"ok")
        probe_path.unlink(missing_ok=True)
        return True
    except OSError:
        return False


class LLMImageTransformation(Transformation):
    """Stage 2: render vocabulary flashcard images from master image prompts."""

    pipeline_stage = "llm"
    required_input_columns = (IMAGE_PROMPT_COLUMN,)

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        output_dir: Optional[str] = None,
        max_retries: int = 3,
        profile_id: str = DEFAULT_LLM_PROFILE_ID,
    ):
        settings = get_settings()
        self.model_name = _resolve_model_name(
            model_name or settings.llm_image_model,
            default=DEFAULT_IMAGE_MODEL,
        )
        self.profile_id = (profile_id or DEFAULT_LLM_PROFILE_ID).strip()
        self.requires_master_prompt = True
        self.fallback_output_dir = Path(FALLBACK_IMAGE_OUTPUT_DIR)
        requested_output_dir = Path(output_dir or settings.image_output_dir)
        self.output_dir = self._resolve_writable_output_dir(requested_output_dir)
        self.max_retries = max_retries
        configured_workers = max(
            1, int(getattr(settings, "llm_image_max_workers", 1) or 1)
        )
        if configured_workers != 1:
            logger.warning(
                "LLM image generation is forced to serial mode (1 worker) to reduce "
                f"RESOURCE_EXHAUSTED errors. Ignoring configured workers={configured_workers}."
            )
        self.max_workers = 1

        self.location = settings.gcp_location
        self.project_id = settings.gcp_project_id
        self.credentials_path = (
            settings.vertex_credentials_path or settings.bq_credentials_path
        )
        self.api_token = _normalize_token(api_key or settings.resolve_llm_api_token())

        try:
            self.client = self._build_genai_client()
        except Exception as exc:
            logger.error(f"Failed to initialize Gemini image client: {exc}")
            raise ValidationError(
                "Gemini credentials are required for image generation. "
                "Set LLM_API_TOKEN (or GEMINI_API_KEY / GOOGLE_API_KEY), "
                "or configure Vertex credentials."
            ) from exc

    @property
    def column_name(self) -> str:
        return "picture"

    def _resolve_writable_output_dir(self, requested_output_dir: Path) -> Path:
        if _directory_is_writable(requested_output_dir):
            return requested_output_dir

        if _directory_is_writable(self.fallback_output_dir):
            logger.warning(
                f"Image output directory '{requested_output_dir}' is not writable. "
                f"Falling back to '{self.fallback_output_dir}'."
            )
            return self.fallback_output_dir

        raise ValidationError(
            "No writable image output directory available. "
            f"Checked '{requested_output_dir}' and '{self.fallback_output_dir}'."
        )

    def _write_image_bytes(
        self, word: str, prompt: str, image_bytes: bytes, extension: str
    ) -> Path:
        filename = f"{self._cache_key(word, prompt)}{extension}"
        primary_path = self.output_dir / filename
        try:
            primary_path.write_bytes(image_bytes)
            return primary_path
        except PermissionError:
            fallback_path = self.fallback_output_dir / filename
            self.fallback_output_dir.mkdir(parents=True, exist_ok=True)
            fallback_path.write_bytes(image_bytes)
            if self.output_dir != self.fallback_output_dir:
                logger.warning(
                    f"Lost write access to '{self.output_dir}'. "
                    f"Writing images to fallback directory '{self.fallback_output_dir}'."
                )
                self.output_dir = self.fallback_output_dir
            return fallback_path

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

    def _build_prompt(self, master_image_prompt: str) -> str:
        return (master_image_prompt or "").strip()

    def _resolve_generator_id(self) -> str:
        if self.profile_id == SP_SPANISH_STANDARD_PROFILE_ID:
            return "spanish_custom_v1"
        return "default_v1"

    def _cache_key(self, word: str, prompt: str) -> str:
        raw = (
            f"{self.model_name}|{self._resolve_generator_id()}|"
            f"{prompt.strip()}|{word.strip()}"
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    def _find_cached_image(self, word: str, prompt: str) -> Optional[Path]:
        cache_key = self._cache_key(word, prompt)
        matches = sorted(self.output_dir.glob(f"{cache_key}.*"))
        if matches:
            return matches[0]
        return None

    def _extract_image_bytes(self, response: object) -> Tuple[bytes, str]:
        candidates = getattr(response, "candidates", []) or []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None) if content else None
            if not parts:
                continue
            for part in parts:
                inline_data = getattr(part, "inline_data", None)
                if not inline_data:
                    continue
                data = getattr(inline_data, "data", None)
                mime_type = getattr(inline_data, "mime_type", None)

                if isinstance(inline_data, dict):
                    data = inline_data.get("data", data)
                    mime_type = inline_data.get("mime_type", mime_type)

                if isinstance(data, str):
                    try:
                        data = base64.b64decode(data)
                    except Exception:
                        data = None

                if isinstance(data, (bytes, bytearray)) and data:
                    return bytes(data), (mime_type or "image/png")
        raise ValueError("Model response did not include image data.")

    def _extension_from_mime(self, mime_type: str) -> str:
        extension = mimetypes.guess_extension(mime_type or "")
        if extension == ".jpe":
            return ".jpg"
        return extension or ".png"

    def _generate_image_default(self, prompt: str) -> Tuple[bytes, str]:
        config = genai_types.GenerateContentConfig(
            temperature=0.2,
            response_modalities=[genai_types.Modality.IMAGE],
        )
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=config,
        )
        return self._extract_image_bytes(response)

    def _generate_image_spanish_custom(self, prompt: str) -> Tuple[bytes, str]:
        # Intentionally uses the same generation request for now.
        return self._generate_image_default(prompt)

    def _generate_image(self, prompt: str) -> Tuple[bytes, str]:
        if self.profile_id == SP_SPANISH_STANDARD_PROFILE_ID:
            return self._generate_image_spanish_custom(prompt)
        return self._generate_image_default(prompt)

    def _build_skipped_result(self, word: str, reason: str) -> Dict[str, Optional[str]]:
        return {
            "word": word,
            self.column_name: None,
            IMAGE_RENDER_STATUS_COLUMN: "skipped",
            IMAGE_RENDER_SKIP_REASON_COLUMN: reason,
        }

    def process_word(
        self,
        word: str,
        master_image_prompt: Optional[str],
        skip_reason: Optional[str] = None,
    ) -> Optional[Dict[str, Optional[str]]]:
        if not word or not word.strip():
            logger.warning("Skipping empty word in LLM image transformation.")
            return None

        safe_word = word.strip()
        if skip_reason and str(skip_reason).strip():
            return self._build_skipped_result(
                safe_word, reason=str(skip_reason).strip()
            )

        prompt = self._build_prompt(master_image_prompt or "")
        if not prompt:
            return self._build_skipped_result(
                safe_word, reason="missing_master_image_prompt"
            )

        cached_image = self._find_cached_image(safe_word, prompt)
        if cached_image:
            return {
                "word": safe_word,
                self.column_name: str(cached_image),
                IMAGE_RENDER_STATUS_COLUMN: "cached",
                IMAGE_RENDER_SKIP_REASON_COLUMN: None,
            }

        try:
            @retry(
                stop=stop_after_attempt(self.max_retries),
                wait=wait_exponential(multiplier=1, min=2, max=10),
                reraise=True,
            )
            def _run_generation() -> Tuple[bytes, str]:
                return self._generate_image(prompt)

            image_bytes, mime_type = _run_generation()
            extension = self._extension_from_mime(mime_type)
            file_path = self._write_image_bytes(
                safe_word, prompt, image_bytes, extension
            )
            return {
                "word": safe_word,
                self.column_name: str(file_path),
                IMAGE_RENDER_STATUS_COLUMN: "generated",
                IMAGE_RENDER_SKIP_REASON_COLUMN: None,
            }
        except Exception as exc:
            logger.error(
                f"Failed to generate image for word '{safe_word}' after retries: {exc}"
            )
            return None

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        logger.info("Applying LLM image transformation...")
        if "word" not in df.columns:
            logger.error("LLMImageTransformation: DataFrame must have a 'word' column.")
            return df

        unique_rows: List[Dict[str, Any]] = []
        seen = set()
        for _, row in df.iterrows():
            word = row.get("word")
            if not word or not str(word).strip():
                continue
            safe_word = str(word).strip()
            if safe_word in seen:
                continue
            seen.add(safe_word)
            unique_rows.append(
                {
                    "word": safe_word,
                    IMAGE_PROMPT_COLUMN: row.get(IMAGE_PROMPT_COLUMN),
                    IMAGE_SKIP_REASON_COLUMN: row.get(IMAGE_SKIP_REASON_COLUMN),
                }
            )

        if not unique_rows:
            logger.warning("LLMImageTransformation: No valid words found to process.")
            return df

        has_prompt_column = IMAGE_PROMPT_COLUMN in df.columns
        if not has_prompt_column:
            logger.warning(
                "LLMImageTransformation: Missing required 'master_image_prompt' column. "
                "Run LLMImagePromptTransformation before image rendering."
            )

        logger.info(
            f"LLM image generation running in serial mode (1 worker) "
            f"for {len(unique_rows)} unique word(s)."
        )

        results = []
        worker_count = min(self.max_workers, len(unique_rows))
        if worker_count <= 1:
            for row in tqdm(unique_rows, desc="LLM Image Processing"):
                results.append(
                    self.process_word(
                        row["word"],
                        row.get(IMAGE_PROMPT_COLUMN),
                        row.get(IMAGE_SKIP_REASON_COLUMN),
                    )
                )
        else:
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                futures = {
                    executor.submit(
                        self.process_word,
                        row["word"],
                        row.get(IMAGE_PROMPT_COLUMN),
                        row.get(IMAGE_SKIP_REASON_COLUMN),
                    ): row["word"]
                    for row in unique_rows
                }
                for future in tqdm(
                    as_completed(futures),
                    total=len(futures),
                    desc="LLM Image Processing",
                ):
                    word = futures[future]
                    try:
                        results.append(future.result())
                    except Exception as exc:
                        logger.error(
                            f"Unexpected parallel image generation failure for '{word}': {exc}"
                        )
                        results.append(None)

        valid_results = [r for r in results if r is not None]
        if not valid_results:
            logger.warning("LLMImageTransformation: No images were generated.")
            return df

        df_results = pd.DataFrame(valid_results).drop_duplicates(subset=["word"])
        if self.column_name not in df_results.columns:
            logger.warning("LLMImageTransformation: No image output column in results.")
            return df

        merge_columns = [
            "word",
            self.column_name,
            IMAGE_RENDER_STATUS_COLUMN,
            IMAGE_RENDER_SKIP_REASON_COLUMN,
        ]
        merge_columns = [col for col in merge_columns if col in df_results.columns]
        df = pd.merge(
            df,
            df_results[merge_columns],
            on="word",
            how="left",
            suffixes=("", "_image"),
        )
        df = df.drop_duplicates(subset=["word"]).reset_index(drop=True)
        logger.info("LLM image transformation applied successfully.")
        return df
