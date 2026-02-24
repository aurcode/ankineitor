from __future__ import annotations

import importlib
import io
import json
import re
import sys
import tempfile
import uuid
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import yaml
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from loguru import logger

from ankineitor.common.pipeline_result_store import (
    list_saved_csv_files_for_profile,
    list_saved_profiles,
)
from ankineitor.pipeline.llm_profiles import DEFAULT_LLM_PROFILE_ID, get_llm_profile
from ankineitor.pipeline.text_extractor import TextExtractor
from ankineitor.security import sanitize_filename, validate_file_upload
from ankineitor.security.exceptions import InvalidFileError, ValidationError

from .models import (
    BackgroundJob,
    BackgroundJobEvent,
    BackgroundJobStatus,
    BackgroundJobType,
    FlashcardDataset,
    FlashcardDatasetSourceType,
    GeneratedAnkiDeck,
    PipelineResultRow,
    PipelineRun,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ALLOWED_WORD_EXTRACTOR_EXTENSIONS = [".pdf", ".docx", ".txt", ".pptx"]
SAFE_DECK_NAME_PATTERN = re.compile(r"^[A-Za-z0-9 _\-]{2,120}$")
JOB_GROUP_PREFIX = "background_job_"
FLASHCARD_ASSET_ALLOWED_DIRS = (
    PROJECT_ROOT / "my_image_files",
    PROJECT_ROOT / "my_audio_files",
    Path(settings.MEDIA_ROOT),
)
FLASHCARD_CUSTOM_IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".webp", ".gif"]
GENERATED_ROW_RERUN_PROCESSES = {
    "full": [],
    "meaning_sentences": ["LLM (Meanings/Sentences)"],
    "audio_word": ["Audio"],
    "audio_sentences": ["LLM (Meanings/Sentences)", "LLM Audio (Sentences)"],
    "image_prompt": ["LLM Image Prompt (Visual Translator)"],
    "image_renderer": ["LLM Image Renderer (Master Prompt)"],
    "image": [
        "LLM Image Prompt (Visual Translator)",
        "LLM Image Renderer (Master Prompt)",
    ],
}
_SENTENCE_AUDIO_COLUMN_PATTERN = re.compile(r"^sentence_\d+_audio$")
HIDDEN_RESULT_COLUMNS = {"pinyin", "translation"}


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()


def _is_remote_asset(value: str) -> bool:
    normalized = str(value or "").strip().lower()
    return normalized.startswith(("http://", "https://", "data:"))


def _remap_known_asset_path(raw_path: str) -> Optional[Path]:
    normalized = str(raw_path or "").strip().replace("\\", "/")
    for directory_name in ("my_image_files", "my_audio_files", "media"):
        marker = f"/{directory_name}/"
        if marker in normalized:
            suffix = normalized.split(marker, 1)[1].lstrip("/")
            return PROJECT_ROOT / directory_name / suffix
        if normalized.endswith(f"/{directory_name}"):
            return PROJECT_ROOT / directory_name
    return None


def resolve_flashcard_asset_path(path_value: str) -> Path:
    raw_path = _safe_text(path_value)
    if not raw_path:
        raise ValueError("Asset path is empty.")
    if _is_remote_asset(raw_path):
        raise ValueError("Remote assets are not served through this endpoint.")

    allowed_roots = [base.resolve() for base in FLASHCARD_ASSET_ALLOWED_DIRS]

    def _is_allowed(resolved_path: Path) -> bool:
        return any(
            resolved_path == allowed_root or allowed_root in resolved_path.parents
            for allowed_root in allowed_roots
        )

    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    resolved = candidate.resolve()
    if _is_allowed(resolved):
        return resolved

    remapped = _remap_known_asset_path(raw_path)
    if remapped is not None:
        remapped_resolved = remapped.resolve()
        if _is_allowed(remapped_resolved):
            return remapped_resolved

    raise ValueError("Asset path is outside allowed directories.")


def _to_json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(key): _to_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_json_safe(item) for item in value]
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if hasattr(value, "item") and callable(getattr(value, "item")):
        try:
            return value.item()
        except Exception:
            pass
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    return value


def _read_csv_with_normalization(csv_bytes: bytes) -> pd.DataFrame:
    loaded_df = pd.read_csv(io.BytesIO(csv_bytes), low_memory=False)
    loaded_df.columns = [str(col).replace("\ufeff", "").strip() for col in loaded_df.columns]
    return loaded_df.astype(object).where(pd.notnull(loaded_df), None)


@lru_cache(maxsize=1)
def _load_anki_templates() -> Dict[str, Any]:
    app_path = PROJECT_ROOT / "app"
    if str(app_path) not in sys.path:
        sys.path.insert(0, str(app_path))

    templates_module = importlib.import_module("tabs.templates")
    return {
        "default_model_templates_yaml": templates_module.DEFAULT_MODEL_TEMPLATES_YAML,
        "default_tag_rules_yaml": templates_module.DEFAULT_TAG_RULES_YAML,
        "chinese_pipeline_setup": templates_module.CHINESE_PIPELINE_SETUP,
    }


class _UploadProxy:
    def __init__(self, name: str, payload: bytes):
        self.name = name
        self._payload = payload

    def getvalue(self) -> bytes:
        return self._payload


DEFAULT_ANKI_CONFIG = {
    "model_id": 1607392319,
    "model_name": "AURCODE Refactored Model",
    "deck_id": 1234567890,
    "note_type": "Vocabulary",
    "model_fields": [
        {"name": "Front"},
        {"name": "Back"},
        {"name": "Example"},
        {"name": "Audio"},
        {"name": "Image"},
        {"name": "Notes"},
    ],
    "model_builder": [
        {"csv_column": "word"},
        {"csv_column": "translation"},
        {"csv_column": "sentence_1"},
        {"csv_column": "audio"},
        {"csv_column": "picture"},
        {"csv_column": "categories"},
    ],
    "media_fields": [
        {"column_name": "audio", "media_type": "audio"},
        {"column_name": "sentence_1_audio", "media_type": "audio"},
        {"column_name": "sentence_2_audio", "media_type": "audio"},
        {"column_name": "sentence_3_audio", "media_type": "audio"},
        {"column_name": "picture", "media_type": "image"},
    ],
}


def get_anki_presets() -> Dict[str, Any]:
    templates = _load_anki_templates()

    default_config = {
        **DEFAULT_ANKI_CONFIG,
        "model_templates_yaml": templates["default_model_templates_yaml"],
        "tag_rules_yaml": templates["default_tag_rules_yaml"],
    }
    chinese_config = templates["chinese_pipeline_setup"]

    return {
        "default": default_config,
        "chinese_pipeline": chinese_config,
    }


def _normalize_anki_config_payload(config_payload: Dict[str, Any]) -> Dict[str, Any]:
    raw_config = dict(config_payload or {})

    model_fields = list(raw_config.get("model_fields") or [])
    if not model_fields:
        raise ValueError("Anki config must include at least one model field.")

    raw_builder = list(raw_config.get("model_builder") or [])
    if not raw_builder:
        raise ValueError("Anki config must include model_builder mappings.")

    model_builder: List[str] = []
    for item in raw_builder:
        if isinstance(item, dict):
            value = _safe_text(item.get("csv_column"))
        else:
            value = _safe_text(item)
        if value:
            model_builder.append(value)

    if len(model_fields) != len(model_builder):
        raise ValueError(
            "Anki config field mismatch: model_fields and model_builder must have equal length."
        )

    media_fields = list(raw_config.get("media_fields") or [])

    model_templates_raw = raw_config.get("model_templates_yaml")
    if isinstance(model_templates_raw, dict):
        model_templates = model_templates_raw
    else:
        try:
            model_templates = yaml.safe_load(str(model_templates_raw or ""))
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid model_templates_yaml: {exc}")
    if not isinstance(model_templates, dict):
        raise ValueError("model_templates_yaml must parse into a dictionary.")

    tag_rules_raw = raw_config.get("tag_rules_yaml")
    if isinstance(tag_rules_raw, list):
        tag_rules = tag_rules_raw
    else:
        try:
            tag_rules = yaml.safe_load(str(tag_rules_raw or ""))
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid tag_rules_yaml: {exc}")
    if not isinstance(tag_rules, list):
        raise ValueError("tag_rules_yaml must parse into a list.")

    return {
        "basics": {
            "model_id": int(raw_config.get("model_id") or DEFAULT_ANKI_CONFIG["model_id"]),
            "model_name": _safe_text(raw_config.get("model_name"))
            or DEFAULT_ANKI_CONFIG["model_name"],
            "deck_id": int(raw_config.get("deck_id") or DEFAULT_ANKI_CONFIG["deck_id"]),
            "note_type": _safe_text(raw_config.get("note_type")) or "Vocabulary",
        },
        "model_fields": model_fields,
        "model_builder": model_builder,
        "media_fields": media_fields,
        "model_templates": model_templates,
        "tag_rules": tag_rules,
    }


def _sanitize_deck_name(raw_name: str) -> str:
    name = _safe_text(raw_name)
    if not name:
        raise ValueError("Deck name is required.")
    if not SAFE_DECK_NAME_PATTERN.fullmatch(name):
        raise ValueError(
            "Deck name contains invalid characters. Use letters, numbers, spaces, hyphens, and underscores."
        )
    return name


def generate_anki_deck_artifact(
    *,
    owner,
    csv_name: str,
    csv_bytes: bytes,
    deck_name: str,
    config_payload: Dict[str, Any],
) -> GeneratedAnkiDeck:
    safe_csv_name = sanitize_filename(csv_name)
    validate_file_upload(_UploadProxy(safe_csv_name, csv_bytes), expected_extensions=[".csv"])

    resolved_deck_name = _sanitize_deck_name(deck_name)
    config = _normalize_anki_config_payload(config_payload)
    df = _read_csv_with_normalization(csv_bytes)
    if df.empty:
        raise ValueError("Uploaded CSV is empty.")

    app_path = PROJECT_ROOT / "app"
    if str(app_path) not in sys.path:
        sys.path.insert(0, str(app_path))

    temp_config_file: Optional[Path] = None
    try:
        try:
            deck_module = importlib.import_module("deck_generator")
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Deck generator dependencies are not installed. Install project requirements first."
            ) from exc

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".yaml",
            prefix="anki_config_",
            delete=False,
            encoding="utf-8",
        ) as handle:
            yaml.dump(config, handle, allow_unicode=True)
            temp_config_file = Path(handle.name)

        output_dir = PROJECT_ROOT / "output" / "anki_decks"
        output_dir.mkdir(parents=True, exist_ok=True)

        deck_generator = deck_module.DeckGenerator(config_path=temp_config_file)
        deck_generator.generate_deck(
            df=df,
            deck_name=resolved_deck_name,
            output_path=output_dir,
            strict=False,
        )

        deck_path = output_dir / f"{resolved_deck_name}.apkg"
        if not deck_path.exists() or not deck_path.is_file():
            raise RuntimeError("Deck generation finished but .apkg was not found.")

        try:
            relative_deck_path = str(deck_path.resolve().relative_to(PROJECT_ROOT.resolve()))
        except Exception:
            relative_deck_path = deck_path.as_posix()

        return GeneratedAnkiDeck.objects.create(
            owner=owner,
            deck_name=resolved_deck_name,
            source_csv_name=safe_csv_name,
            output_path=relative_deck_path,
            file_size_bytes=int(deck_path.stat().st_size),
        )
    finally:
        if temp_config_file and temp_config_file.exists():
            temp_config_file.unlink(missing_ok=True)


def resolve_anki_artifact_path(artifact: GeneratedAnkiDeck) -> Path:
    path = Path(artifact.output_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    resolved = path.resolve()
    if PROJECT_ROOT.resolve() not in resolved.parents:
        raise ValueError("Deck path is outside workspace.")
    return resolved


def list_flashcard_saved_profiles() -> List[str]:
    saved_profiles = list_saved_profiles()
    ordered_profiles = [DEFAULT_LLM_PROFILE_ID]
    ordered_profiles.extend(
        profile for profile in saved_profiles if profile != DEFAULT_LLM_PROFILE_ID
    )
    return ordered_profiles


def list_flashcard_saved_files(profile_id: str) -> List[Dict[str, Any]]:
    saved_files = list_saved_csv_files_for_profile(profile_id)
    payload: List[Dict[str, Any]] = []
    for file_path in saved_files:
        try:
            stats = file_path.stat()
            modified_at = datetime.fromtimestamp(stats.st_mtime).isoformat()
            size_bytes = int(stats.st_size)
        except OSError:
            modified_at = None
            size_bytes = 0

        payload.append(
            {
                "file_name": file_path.name,
                "file_path": file_path.as_posix(),
                "modified_at": modified_at,
                "size_bytes": size_bytes,
            }
        )
    return payload


def _normalize_reviewer_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    normalized.columns = [str(col).replace("\ufeff", "").strip() for col in normalized.columns]
    return normalized.astype(object).where(pd.notnull(normalized), None)


def _read_dataset_csv_bytes(file_bytes: bytes) -> pd.DataFrame:
    loaded = pd.read_csv(io.BytesIO(file_bytes), low_memory=False)
    return _normalize_reviewer_dataframe(loaded)


def _read_dataset_from_path(path: Path) -> pd.DataFrame:
    loaded = pd.read_csv(path, low_memory=False)
    return _normalize_reviewer_dataframe(loaded)


@lru_cache(maxsize=32)
def _load_dataset_cache(path_str: str, mtime_ns: int, size: int) -> pd.DataFrame:
    del mtime_ns, size
    return _read_dataset_from_path(Path(path_str))


def _resolve_dataset_csv_path(dataset: FlashcardDataset) -> Path:
    csv_path = Path(dataset.csv_path)
    if not csv_path.is_absolute():
        csv_path = PROJECT_ROOT / csv_path
    return csv_path.resolve()


def _load_dataset_dataframe(dataset: FlashcardDataset) -> pd.DataFrame:
    csv_path = _resolve_dataset_csv_path(dataset)
    stats = csv_path.stat()
    cached = _load_dataset_cache(csv_path.as_posix(), int(stats.st_mtime_ns), int(stats.st_size))
    return cached.copy()


def _persist_dataset_dataframe(dataset: FlashcardDataset, df: pd.DataFrame) -> pd.DataFrame:
    csv_path = _resolve_dataset_csv_path(dataset)
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    normalized = _normalize_reviewer_dataframe(df)
    normalized.to_csv(csv_path, index=False)
    _load_dataset_cache.cache_clear()

    dataset.total_cards = int(len(normalized))
    dataset.columns = list(normalized.columns)
    dataset.save(update_fields=["total_cards", "columns"])
    return normalized


def _resolve_card_source_index(
    *,
    df: pd.DataFrame,
    index: int,
    profile_filter: Optional[str],
) -> Tuple[int, int, int]:
    indexed = df.reset_index(drop=False).rename(columns={"index": "__source_index"})

    normalized_filter = _safe_text(profile_filter)
    if normalized_filter and normalized_filter != "All profiles" and "profile_id" in indexed.columns:
        indexed = (
            indexed[indexed["profile_id"].astype(str).str.strip() == normalized_filter]
            .copy()
            .reset_index(drop=True)
        )

    if indexed.empty:
        raise ValueError("No cards available for this dataset/filter.")

    safe_index = max(0, min(int(index), len(indexed) - 1))
    source_index = int(indexed.iloc[safe_index]["__source_index"])
    return source_index, safe_index, len(indexed)


def _dataset_summary_payload(dataset: FlashcardDataset, df: pd.DataFrame) -> Dict[str, Any]:
    available_profiles: List[str] = []
    if "profile_id" in df.columns:
        available_profiles = sorted(
            df["profile_id"]
            .astype(str)
            .str.strip()
            .replace("", pd.NA)
            .dropna()
            .unique()
            .tolist()
        )

    return {
        "dataset_id": str(dataset.id),
        "source_type": dataset.source_type,
        "source_label": dataset.source_label,
        "total_cards": int(len(df)),
        "columns": list(df.columns),
        "available_profiles": available_profiles,
        "created_at": dataset.created_at.isoformat(),
    }


def create_flashcard_dataset_from_saved(
    *,
    owner,
    profile_id: str,
    file_name: Optional[str],
) -> Dict[str, Any]:
    profiles = set(list_saved_profiles())
    if profile_id not in profiles:
        raise ValueError(f"Unknown saved profile '{profile_id}'.")

    files = list_saved_csv_files_for_profile(profile_id)
    if not files:
        raise ValueError(f"No saved CSV files found for profile '{profile_id}'.")

    selected_path: Optional[Path] = None
    requested_name = _safe_text(file_name)
    if requested_name:
        for candidate in files:
            if candidate.name == requested_name or candidate.as_posix() == requested_name:
                selected_path = candidate
                break
        if selected_path is None:
            raise ValueError(f"Saved CSV '{requested_name}' not found for profile '{profile_id}'.")
    else:
        selected_path = files[0]

    df = _read_dataset_from_path(selected_path)
    try:
        csv_relative = str(selected_path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except Exception:
        csv_relative = selected_path.as_posix()

    dataset = FlashcardDataset.objects.create(
        owner=owner,
        source_type=FlashcardDatasetSourceType.SAVED,
        source_label=f"{profile_id}:{selected_path.name}",
        csv_path=csv_relative,
        total_cards=int(len(df)),
        columns=list(df.columns),
    )
    return _dataset_summary_payload(dataset, df)


def create_flashcard_dataset_from_upload(*, owner, file_name: str, file_bytes: bytes) -> Dict[str, Any]:
    safe_name = sanitize_filename(file_name)
    validate_file_upload(_UploadProxy(safe_name, file_bytes), expected_extensions=[".csv"])

    df = _read_dataset_csv_bytes(file_bytes)
    if df.empty:
        raise ValueError("Uploaded CSV is empty.")

    upload_dir = Path(settings.MEDIA_ROOT) / "flashcard_uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    dataset_id = FlashcardDataset.objects.create(
        owner=owner,
        source_type=FlashcardDatasetSourceType.UPLOAD,
        source_label=safe_name,
        csv_path="pending",
        total_cards=0,
        columns=[],
    ).id

    stored_name = f"{dataset_id}_{safe_name}"
    file_path = upload_dir / stored_name
    file_path.write_bytes(file_bytes)

    try:
        csv_relative = str(file_path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except Exception:
        csv_relative = file_path.as_posix()

    dataset = FlashcardDataset.objects.get(pk=dataset_id)
    dataset.csv_path = csv_relative
    dataset.total_cards = int(len(df))
    dataset.columns = list(df.columns)
    dataset.save(update_fields=["csv_path", "total_cards", "columns"])

    return _dataset_summary_payload(dataset, df)


def get_flashcard_dataset_summary(dataset_id: str, owner) -> Dict[str, Any]:
    dataset = FlashcardDataset.objects.get(pk=dataset_id, owner=owner)
    df = _load_dataset_dataframe(dataset)
    return _dataset_summary_payload(dataset, df)


def _first_non_empty(row: pd.Series, columns: List[str]) -> str:
    for column_name in columns:
        value = _safe_text(row.get(column_name))
        if value:
            return value
    return ""


def _try_parse_json(raw_value: Any) -> Any:
    if isinstance(raw_value, (dict, list)):
        return raw_value
    text = _safe_text(raw_value)
    if not text:
        return None

    candidate = text
    for _ in range(3):
        stripped = candidate.strip()
        fenced = re.match(r"^\s*```(?:json|JSON)?\s*(.*?)\s*```\s*$", stripped, flags=re.DOTALL)
        if fenced:
            stripped = fenced.group(1).strip()
        try:
            parsed = json.loads(stripped)
        except Exception:
            return None
        if isinstance(parsed, str):
            candidate = parsed
            continue
        return parsed
    return None


def _json_item_to_text(item: Any) -> str:
    if isinstance(item, dict):
        parts: List[str] = []
        for key, value in item.items():
            if isinstance(value, (dict, list)):
                value_text = json.dumps(value, ensure_ascii=False)
            else:
                value_text = _safe_text(value)
            if value_text:
                parts.append(f"{key}: {value_text}")
        if parts:
            return " | ".join(parts)
        return json.dumps(item, ensure_ascii=False)
    if isinstance(item, list):
        nested_values = [_json_item_to_text(value) for value in item]
        nested_values = [value for value in nested_values if value]
        return " | ".join(nested_values)
    return _safe_text(item)


def _parse_json_list(raw_value: Any) -> List[str]:
    parsed = _try_parse_json(raw_value)
    if isinstance(parsed, list):
        values = [_json_item_to_text(item) for item in parsed]
        return [value for value in values if value]
    if isinstance(parsed, dict):
        return [_json_item_to_text(parsed)]
    return []


def _list_from_columns(row: pd.Series, json_col: str, rendered_col: str) -> List[str]:
    parsed = _parse_json_list(row.get(json_col))
    if parsed:
        return parsed

    rendered = _safe_text(row.get(rendered_col))
    if not rendered:
        return []
    return [item.strip() for item in rendered.split("|") if item.strip()]


def _find_sentence_indexes(row: pd.Series) -> List[int]:
    indexes: List[int] = []
    sentence_pattern = re.compile(r"^sentence_(\d+)$")
    tts_pattern = re.compile(r"^sentence_(\d+)_tts_clean$")

    for col_name in row.index:
        col = str(col_name)
        sentence_match = sentence_pattern.match(col)
        if sentence_match and _safe_text(row.get(col)):
            indexes.append(int(sentence_match.group(1)))
            continue
        tts_match = tts_pattern.match(col)
        if tts_match and _safe_text(row.get(col)):
            indexes.append(int(tts_match.group(1)))

    return sorted(set(indexes))


def _sentence_entries_from_columns(row: pd.Series) -> List[Dict[str, str]]:
    entries: List[Dict[str, str]] = []
    for idx in _find_sentence_indexes(row):
        entries.append(
            {
                "index": str(idx),
                "sentence": _safe_text(row.get(f"sentence_{idx}")),
                "tts_clean": _safe_text(row.get(f"sentence_{idx}_tts_clean")),
                "cloze": _safe_text(row.get(f"sentence_{idx}_cloze")),
                "pronunciation": _first_non_empty(
                    row,
                    [
                        f"sentence_{idx}_pinyin",
                        f"sentence_{idx}_romanization",
                        f"sentence_{idx}_pronunciation_hint",
                    ],
                ),
                "translation_english": _safe_text(row.get(f"sentence_{idx}_translation_english")),
                "translation_spanish": _safe_text(row.get(f"sentence_{idx}_translation_spanish")),
                "audio": _safe_text(row.get(f"sentence_{idx}_audio")),
            }
        )
    return entries


def _sentence_entries_from_json(row: pd.Series) -> List[Dict[str, str]]:
    parsed_json = _try_parse_json(row.get("sentences_json"))
    if isinstance(parsed_json, dict):
        nested_sentences = parsed_json.get("sentences")
        if isinstance(nested_sentences, list):
            parsed_json = nested_sentences

    if not isinstance(parsed_json, list):
        return []

    entries: List[Dict[str, str]] = []
    for idx, item in enumerate(parsed_json, start=1):
        if isinstance(item, dict):
            item_series = pd.Series(item)
            entries.append(
                {
                    "index": str(idx),
                    "sentence": _first_non_empty(item_series, ["target_language_highlighted", "sentence", "text"]),
                    "tts_clean": _safe_text(item.get("tts_clean_sentence")),
                    "cloze": _safe_text(item.get("target_language_cloze")),
                    "pronunciation": _first_non_empty(
                        item_series,
                        [
                            "sentence_pinyin",
                            "sentence_romanization",
                            "sentence_pronunciation_hint",
                            "romanization",
                        ],
                    ),
                    "translation_english": _safe_text(item.get("translation_english")),
                    "translation_spanish": _safe_text(item.get("translation_spanish")),
                    "audio": "",
                }
            )
        else:
            text = _json_item_to_text(item)
            if text:
                entries.append(
                    {
                        "index": str(idx),
                        "sentence": text,
                        "tts_clean": "",
                        "cloze": "",
                        "pronunciation": "",
                        "translation_english": "",
                        "translation_spanish": "",
                        "audio": "",
                    }
                )
    return entries


def _build_flashcard_card_payload(row: pd.Series, index: int, total: int) -> Dict[str, Any]:
    front = {
        "word": _first_non_empty(row, ["word_with_stress", "word_model", "word"]),
        "pronunciation": _first_non_empty(row, ["pinyin_llm", "pinyin", "romanization"]),
        "part_of_speech": _safe_text(row.get("part_of_speech")),
        "register": _safe_text(row.get("register")),
        "profile_id": _safe_text(row.get("profile_id")),
        "timestamp": _safe_text(row.get("timestamp")),
        "audio": _safe_text(row.get("audio")),
    }

    details = {
        "lemma": _safe_text(row.get("lemma")),
        "pronunciation_ipa": _safe_text(row.get("pronunciation_ipa")),
        "syllabification_and_stress": _safe_text(row.get("syllabification_and_stress")),
        "regional_scope": _safe_text(row.get("regional_scope")),
        "aspect_pair": _safe_text(row.get("aspect_pair")),
        "grammar_formula": _safe_text(row.get("grammar_formula")),
        "ser_estar_note": _safe_text(row.get("ser_estar_note")),
        "por_para_note": _safe_text(row.get("por_para_note")),
        "reflexive_variant": _safe_text(row.get("reflexive_variant")),
        "irregular_forms": _safe_text(row.get("irregular_forms_json")),
        "common_mistakes": _safe_text(row.get("common_mistakes_json")),
        "character_breakdown": _safe_text(row.get("character_breakdown")),
        "mnemonic_hook_spanish": _safe_text(row.get("mnemonic_hook_spanish")),
        "piter_summer_variant": _safe_text(row.get("piter_summer_variant")),
        "edge_case_notes": _safe_text(row.get("edge_case_notes")),
        "improved_meaning": _safe_text(row.get("improved_meaning")),
        "example_sentences": _safe_text(row.get("example_sentences")),
        "categories": _safe_text(row.get("categories")),
        "profile_version": _safe_text(row.get("profile_version")),
    }

    relationships = {
        "synonyms": _list_from_columns(row, "synonyms_json", "synonyms_rendered"),
        "antonyms": _list_from_columns(row, "antonyms_json", "antonyms_rendered"),
        "collocations": _list_from_columns(row, "collocations_json", "collocations_rendered"),
    }

    sentences = _sentence_entries_from_columns(row)
    if not sentences:
        sentences = _sentence_entries_from_json(row)

    image_metadata = {
        "picture": _safe_text(row.get("picture")),
        "image_term_type": _safe_text(row.get("image_term_type")),
        "visual_description": _safe_text(row.get("visual_description")),
        "master_image_prompt": _safe_text(row.get("master_image_prompt")),
        "image_generation_skip_reason": _safe_text(row.get("image_generation_skip_reason")),
        "image_render_status": _safe_text(row.get("image_render_status")),
        "image_render_skip_reason": _safe_text(row.get("image_render_skip_reason")),
    }

    back = {
        "meaning_english": _first_non_empty(
            row,
            [
                "meaning_english",
                "detailed_explanation_english",
                "translation_llm",
                "translation",
            ],
        ),
        "meaning_spanish": _first_non_empty(
            row,
            ["meaning_spanish", "detailed_explanation_spanish"],
        ),
        "details": details,
        "relationships": relationships,
        "sentences": sentences,
        "image": image_metadata,
    }

    raw_row = {str(key): _to_json_safe(value) for key, value in row.to_dict().items()}
    return {
        "index": index,
        "total": total,
        "front": front,
        "back": back,
        "raw_row": raw_row,
    }


def get_flashcard_card(
    *,
    dataset_id: str,
    owner,
    index: int,
    profile_filter: Optional[str],
) -> Dict[str, Any]:
    dataset = FlashcardDataset.objects.get(pk=dataset_id, owner=owner)
    df = _load_dataset_dataframe(dataset)
    source_index, safe_index, filtered_total = _resolve_card_source_index(
        df=df,
        index=index,
        profile_filter=profile_filter,
    )
    row = df.iloc[source_index]
    return _build_flashcard_card_payload(row=row, index=safe_index, total=filtered_total)


def update_flashcard_card_fields(
    *,
    dataset_id: str,
    owner,
    index: int,
    profile_filter: Optional[str],
    updates: Dict[str, Any],
) -> Dict[str, Any]:
    dataset = FlashcardDataset.objects.get(pk=dataset_id, owner=owner)
    df = _load_dataset_dataframe(dataset)
    source_index, safe_index, filtered_total = _resolve_card_source_index(
        df=df,
        index=index,
        profile_filter=profile_filter,
    )

    normalized_updates: Dict[str, Any] = {}
    for raw_key, raw_value in dict(updates or {}).items():
        key = _safe_text(raw_key)
        if not key:
            continue
        normalized_updates[key] = raw_value
    if not normalized_updates:
        raise ValueError("Provide at least one field to update.")

    for key, value in normalized_updates.items():
        df.at[source_index, key] = value

    persisted = _persist_dataset_dataframe(dataset, df)
    row = persisted.iloc[source_index]
    return {
        "dataset": _dataset_summary_payload(dataset, persisted),
        "card": _build_flashcard_card_payload(row=row, index=safe_index, total=filtered_total),
    }


def upload_flashcard_card_custom_image(
    *,
    dataset_id: str,
    owner,
    index: int,
    profile_filter: Optional[str],
    file_name: str,
    file_bytes: bytes,
) -> Dict[str, Any]:
    safe_name = sanitize_filename(file_name)
    validate_file_upload(
        _UploadProxy(safe_name, file_bytes),
        expected_extensions=FLASHCARD_CUSTOM_IMAGE_EXTENSIONS,
    )

    target_dir = Path(settings.MEDIA_ROOT) / "flashcard_custom_images" / str(dataset_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}_{safe_name}"
    target_path = target_dir / stored_name
    target_path.write_bytes(file_bytes)

    try:
        stored_path = str(target_path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except Exception:
        stored_path = target_path.as_posix()

    return update_flashcard_card_fields(
        dataset_id=dataset_id,
        owner=owner,
        index=index,
        profile_filter=profile_filter,
        updates={
            "picture": stored_path,
            "image_render_status": "custom_upload",
            "image_render_skip_reason": "",
            "image_generation_skip_reason": "",
        },
    )


def rerun_flashcard_card_generation(
    *,
    dataset_id: str,
    owner,
    index: int,
    profile_filter: Optional[str],
    mode: str,
) -> Dict[str, Any]:
    dataset = FlashcardDataset.objects.get(pk=dataset_id, owner=owner)
    df = _load_dataset_dataframe(dataset)
    source_index, safe_index, filtered_total = _resolve_card_source_index(
        df=df,
        index=index,
        profile_filter=profile_filter,
    )

    row = df.iloc[source_index]
    word = _safe_text(row.get("word"))
    if not word:
        raise ValueError("Selected card does not contain a word value.")

    profile_id = _safe_text(row.get("profile_id")) or DEFAULT_LLM_PROFILE_ID
    try:
        selected_profile = get_llm_profile(profile_id)
        profile_id = selected_profile.profile_id
    except Exception:
        selected_profile = get_llm_profile(DEFAULT_LLM_PROFILE_ID)
        profile_id = selected_profile.profile_id

    selected_transform_names: List[str]
    normalized_mode = _safe_text(mode).lower()
    if normalized_mode == "image":
        selected_transform_names = [
            "LLM Image Prompt (Visual Translator)",
            "LLM Image Renderer (Master Prompt)",
        ]
    elif normalized_mode == "full":
        selected_transform_names = []
    else:
        raise ValueError("mode must be one of: full, image.")

    from .services import get_pipeline_runtime, resolve_ordered_transform_names

    runtime = get_pipeline_runtime()
    (
        resolved_selected_transforms,
        ordered_transform_names,
        source_language,
    ) = resolve_ordered_transform_names(
        profile_id=profile_id,
        selected_transform_names=selected_transform_names,
    )

    from ankineitor.application import PipelineRunService

    pipeline_service = PipelineRunService()
    prepared_run = pipeline_service.prepare_pipeline_run(
        pipeline_db_client=runtime.pipeline_db_client,
        all_transformations=runtime.all_transformations,
        ordered_transform_names=ordered_transform_names,
        llm_profile_id=profile_id,
        llm_source_language=source_language,
        transform_factory=runtime.transform_factory,
        table_name="hanzi_processing",
    )
    run_result = pipeline_service.execute_pipeline_run(
        prepared_run=prepared_run,
        words=[word],
        llm_profile_id=profile_id,
        progress_callback=None,
        dev_mode=False,
        execution_mode="parallel_word_branches",
    )
    if run_result.df_results.empty:
        raise ValueError("Rerun did not produce any result rows.")

    generated_row = run_result.df_results.iloc[0].to_dict()
    if normalized_mode == "image":
        columns_to_replace = {
            "master_image_prompt",
            "visual_description",
            "image_term_type",
            "picture",
            "image_generation_skip_reason",
            "image_render_status",
            "image_render_skip_reason",
        }
    else:
        columns_to_replace = {
            str(column)
            for column in generated_row.keys()
            if str(column) not in {"word", "timestamp", "categories"}
        }

    for column_name in columns_to_replace:
        if column_name not in generated_row:
            continue
        df.at[source_index, column_name] = generated_row.get(column_name)

    df.at[source_index, "profile_id"] = profile_id
    persisted = _persist_dataset_dataframe(dataset, df)
    updated_row = persisted.iloc[source_index]
    return {
        "dataset": _dataset_summary_payload(dataset, persisted),
        "card": _build_flashcard_card_payload(
            row=updated_row,
            index=safe_index,
            total=filtered_total,
        ),
        "rerun_mode": normalized_mode,
        "applied_transforms": resolved_selected_transforms,
    }


def _normalize_result_row_payload(
    payload: Dict[str, Any],
    *,
    fallback_timestamp: str,
) -> Dict[str, Any]:
    normalized = {
        str(key): _to_json_safe(value)
        for key, value in dict(payload or {}).items()
        if str(key) not in HIDDEN_RESULT_COLUMNS
    }
    if not _safe_text(normalized.get("timestamp")):
        normalized["timestamp"] = fallback_timestamp
    return normalized


def _rewrite_pipeline_run_results_csv(run: PipelineRun) -> None:
    csv_output_path = _safe_text(run.csv_output_path)
    if not csv_output_path:
        return

    csv_path = Path(csv_output_path)
    if not csv_path.is_absolute():
        csv_path = PROJECT_ROOT / csv_path
    resolved_csv_path = csv_path.resolve()
    if PROJECT_ROOT.resolve() not in resolved_csv_path.parents:
        logger.warning(
            "Skipping CSV rewrite for run {} because path is outside workspace: {}",
            run.id,
            resolved_csv_path,
        )
        return

    records = [
        dict(row.row_data or {})
        for row in PipelineResultRow.objects.filter(run=run).order_by("row_index")
    ]
    if not records:
        return

    resolved_csv_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(records).to_csv(resolved_csv_path, index=False)


def _build_generated_row_detail_payload(row: PipelineResultRow) -> Dict[str, Any]:
    fallback_timestamp = (
        row.created_at.isoformat() if row.created_at else timezone.now().isoformat()
    )
    normalized_row_data = _normalize_result_row_payload(
        dict(row.row_data or {}),
        fallback_timestamp=fallback_timestamp,
    )
    row.row_data = normalized_row_data
    row.word = _safe_text(normalized_row_data.get("word")) or _safe_text(row.word)

    total_in_run = PipelineResultRow.objects.filter(run=row.run).count()
    card_payload = _build_flashcard_card_payload(
        row=pd.Series(normalized_row_data),
        index=int(row.row_index or 0),
        total=max(total_in_run, 1),
    )
    return {
        "row_id": int(row.id),
        "run_id": str(row.run_id),
        "run_status": _safe_text(row.run.status),
        "profile_id": _safe_text(normalized_row_data.get("profile_id")) or _safe_text(row.run.profile_id),
        "row_index": int(row.row_index or 0),
        "word": _safe_text(row.word),
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "row_data": normalized_row_data,
        "card": card_payload,
    }


def get_generated_row_detail(*, row_id: int, owner) -> Dict[str, Any]:
    row = PipelineResultRow.objects.select_related("run").get(pk=row_id, run__owner=owner)
    return _build_generated_row_detail_payload(row)


def update_generated_row_fields(
    *,
    row_id: int,
    owner,
    updates: Dict[str, Any],
) -> Dict[str, Any]:
    row = PipelineResultRow.objects.select_related("run").get(pk=row_id, run__owner=owner)

    normalized_updates: Dict[str, Any] = {}
    for raw_key, raw_value in dict(updates or {}).items():
        key = _safe_text(raw_key)
        if not key:
            continue
        normalized_updates[key] = raw_value
    if not normalized_updates:
        raise ValueError("Provide at least one field to update.")

    fallback_timestamp = (
        row.created_at.isoformat() if row.created_at else timezone.now().isoformat()
    )
    row_payload = _normalize_result_row_payload(
        dict(row.row_data or {}),
        fallback_timestamp=fallback_timestamp,
    )
    row_payload.update(normalized_updates)
    row_payload = _normalize_result_row_payload(row_payload, fallback_timestamp=fallback_timestamp)

    normalized_word = _safe_text(row_payload.get("word")) or _safe_text(row.word)
    row_payload["word"] = normalized_word
    row.word = normalized_word
    row.row_data = row_payload
    row.save(update_fields=["word", "row_data"])
    _rewrite_pipeline_run_results_csv(row.run)
    return _build_generated_row_detail_payload(row)


def upload_generated_row_custom_image(
    *,
    row_id: int,
    owner,
    file_name: str,
    file_bytes: bytes,
) -> Dict[str, Any]:
    row = PipelineResultRow.objects.select_related("run").get(pk=row_id, run__owner=owner)

    safe_name = sanitize_filename(file_name)
    validate_file_upload(
        _UploadProxy(safe_name, file_bytes),
        expected_extensions=FLASHCARD_CUSTOM_IMAGE_EXTENSIONS,
    )

    target_dir = Path(settings.MEDIA_ROOT) / "generated_row_custom_images" / str(row.run_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}_{safe_name}"
    target_path = target_dir / stored_name
    target_path.write_bytes(file_bytes)

    try:
        stored_path = str(target_path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except Exception:
        stored_path = target_path.as_posix()

    return update_generated_row_fields(
        row_id=row_id,
        owner=owner,
        updates={
            "picture": stored_path,
            "image_render_status": "custom_upload",
            "image_render_skip_reason": "",
            "image_generation_skip_reason": "",
        },
    )


def _columns_to_replace_for_generated_rerun(
    *,
    process: str,
    generated_row: Dict[str, Any],
    current_row: Optional[Dict[str, Any]] = None,
) -> set[str]:
    all_generated_columns = {str(column) for column in generated_row.keys()}
    all_current_columns = {str(column) for column in dict(current_row or {}).keys()}
    if process == "full":
        return {
            column
            for column in all_generated_columns
            if column not in {"word", "timestamp", "categories"}
        }
    if process == "audio_word":
        return {"audio"}
    if process == "audio_sentences":
        generated_audio_columns = {
            column
            for column in all_generated_columns
            if _SENTENCE_AUDIO_COLUMN_PATTERN.match(column)
        }
        existing_audio_columns = {
            column
            for column in all_current_columns
            if _SENTENCE_AUDIO_COLUMN_PATTERN.match(column)
        }
        return generated_audio_columns | existing_audio_columns
    if process == "image_prompt":
        return {
            "image_term_type",
            "visual_description",
            "master_image_prompt",
            "image_generation_skip_reason",
        }
    if process == "image_renderer":
        return {"picture", "image_render_status", "image_render_skip_reason"}
    if process == "image":
        return {
            "image_term_type",
            "visual_description",
            "master_image_prompt",
            "image_generation_skip_reason",
            "picture",
            "image_render_status",
            "image_render_skip_reason",
        }
    if process == "meaning_sentences":
        llm_columns = {
            "lemma",
            "pronunciation_ipa",
            "syllabification_and_stress",
            "regional_scope",
            "ser_estar_note",
            "por_para_note",
            "reflexive_variant",
            "irregular_forms_json",
            "common_mistakes_json",
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
            "meaning_english",
            "meaning_spanish",
        }
        return {
            column
            for column in all_generated_columns
            if column in llm_columns
            or (
                column.startswith("sentence_")
                and not _SENTENCE_AUDIO_COLUMN_PATTERN.match(column)
            )
        }
    return set()


def _rerun_process_dataframe_without_cache(
    *,
    prepared_run,
    word: str,
    transform_names: List[str],
    seed_row: Optional[Dict[str, Any]] = None,
) -> pd.DataFrame:
    transform_by_name = {
        str(name): transform
        for name, transform in zip(
            list(getattr(prepared_run, "ordered_transform_names", []) or []),
            list(getattr(prepared_run, "selected_transforms", []) or []),
        )
    }

    seed_payload = {
        str(key): value for key, value in dict(seed_row or {}).items() if str(key).strip()
    }
    seed_payload["word"] = word
    rerun_df = pd.DataFrame([seed_payload])
    for transform_name in transform_names:
        transform = transform_by_name.get(str(transform_name))
        if transform is None:
            continue
        output_df = transform.apply(rerun_df)
        if output_df is None:
            continue
        rerun_df = output_df
    return rerun_df


def rerun_generated_row_process(
    *,
    row_id: int,
    owner,
    process: str,
) -> Dict[str, Any]:
    row = PipelineResultRow.objects.select_related("run").get(pk=row_id, run__owner=owner)
    normalized_process = _safe_text(process).lower() or "full"
    if normalized_process not in GENERATED_ROW_RERUN_PROCESSES:
        supported = ", ".join(sorted(GENERATED_ROW_RERUN_PROCESSES.keys()))
        raise ValueError(f"Unsupported process '{normalized_process}'. Supported: {supported}.")

    fallback_timestamp = (
        row.created_at.isoformat() if row.created_at else timezone.now().isoformat()
    )
    row_payload = _normalize_result_row_payload(
        dict(row.row_data or {}),
        fallback_timestamp=fallback_timestamp,
    )
    word = _safe_text(row_payload.get("word")) or _safe_text(row.word)
    if not word:
        raise ValueError("Selected DB row does not contain a word value.")

    profile_id = _safe_text(row_payload.get("profile_id")) or _safe_text(row.run.profile_id)
    if not profile_id:
        profile_id = DEFAULT_LLM_PROFILE_ID
    try:
        selected_profile = get_llm_profile(profile_id)
        profile_id = selected_profile.profile_id
    except Exception:
        selected_profile = get_llm_profile(DEFAULT_LLM_PROFILE_ID)
        profile_id = selected_profile.profile_id

    selected_transform_names = list(GENERATED_ROW_RERUN_PROCESSES[normalized_process])

    from .services import get_pipeline_runtime, resolve_ordered_transform_names

    runtime = get_pipeline_runtime()
    (
        resolved_selected_transforms,
        ordered_transform_names,
        source_language,
    ) = resolve_ordered_transform_names(
        profile_id=profile_id,
        selected_transform_names=selected_transform_names,
    )

    from ankineitor.application import PipelineRunService

    pipeline_service = PipelineRunService()
    prepared_run = pipeline_service.prepare_pipeline_run(
        pipeline_db_client=runtime.pipeline_db_client,
        all_transformations=runtime.all_transformations,
        ordered_transform_names=ordered_transform_names,
        llm_profile_id=profile_id,
        llm_source_language=source_language,
        transform_factory=runtime.transform_factory,
        table_name="hanzi_processing",
    )
    if normalized_process in {"audio_word", "audio_sentences"}:
        rerun_df_results = _rerun_process_dataframe_without_cache(
            prepared_run=prepared_run,
            word=word,
            transform_names=selected_transform_names,
            seed_row=row_payload,
        )
    else:
        run_result = pipeline_service.execute_pipeline_run(
            prepared_run=prepared_run,
            words=[word],
            llm_profile_id=profile_id,
            progress_callback=None,
            dev_mode=False,
            execution_mode="parallel_word_branches",
        )
        rerun_df_results = run_result.df_results

    if rerun_df_results.empty:
        raise ValueError("Rerun did not produce any result rows.")

    generated_row = rerun_df_results.iloc[0].to_dict()
    columns_to_replace = _columns_to_replace_for_generated_rerun(
        process=normalized_process,
        generated_row=generated_row,
        current_row=row_payload,
    )
    for column_name in columns_to_replace:
        row_payload[column_name] = generated_row.get(column_name)

    row_payload["profile_id"] = profile_id
    row_payload["word"] = word
    row_payload = _normalize_result_row_payload(row_payload, fallback_timestamp=fallback_timestamp)

    row.word = word
    row.row_data = row_payload
    row.save(update_fields=["word", "row_data"])
    _rewrite_pipeline_run_results_csv(row.run)

    payload = _build_generated_row_detail_payload(row)
    payload["rerun_process"] = normalized_process
    payload["applied_transforms"] = resolved_selected_transforms
    return payload


def _records_from_dataframe(df: pd.DataFrame) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for row in df.to_dict(orient="records"):
        rows.append({str(key): _to_json_safe(value) for key, value in row.items()})
    return rows


def _filter_dataframe_hsk(
    df: pd.DataFrame,
    filters: Dict[str, pd.DataFrame],
    filter_column_name: str,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    if filter_column_name not in df.columns:
        raise KeyError(f"Column '{filter_column_name}' not found in DataFrame.")

    remaining_df = df.copy()
    removed_chunks: List[pd.DataFrame] = []

    for level, filter_df in filters.items():
        if "hanzi" not in filter_df.columns:
            continue
        hsk_words = set(filter_df["hanzi"])
        is_in_level = remaining_df[filter_column_name].isin(hsk_words)
        if not is_in_level.any():
            continue

        removed_chunk = remaining_df[is_in_level].copy()
        removed_chunk["hsk_level"] = level.upper()
        removed_chunks.append(removed_chunk)
        remaining_df = remaining_df[~is_in_level]

    if removed_chunks:
        removed_df = pd.concat(removed_chunks, ignore_index=True)
    else:
        removed_df = pd.DataFrame(columns=list(df.columns) + ["hsk_level"])

    return remaining_df, removed_df


@lru_cache(maxsize=1)
def load_hsk_filters() -> Dict[str, pd.DataFrame]:
    columns = ["hanzi", "tradicional", "pinyin1", "pinyin2", "space", "mean"]
    filters = {
        "hsk1": pd.read_csv(
            "https://raw.githubusercontent.com/aurcode/chinese-words/main/Chinese__HSK-1.txt",
            sep="\t",
            names=columns,
        ),
        "hsk2": pd.read_csv(
            "https://raw.githubusercontent.com/aurcode/chinese-words/main/Chinese__HSK-2.txt",
            sep="\t",
            names=columns,
        ),
        "hsk3": pd.read_csv(
            "https://raw.githubusercontent.com/aurcode/chinese-words/main/Chinese__HSK-3.txt",
            sep="\t",
            names=columns,
        ),
        "hsk4": pd.read_csv(
            "https://raw.githubusercontent.com/aurcode/chinese-words/main/Chinese__HSK-4.txt",
            sep="\t",
            names=columns,
        ),
    }

    df_ting = pd.read_csv(
        "https://raw.githubusercontent.com/aurcode/chinese-words/main/hsk-5-vocabulary.csv",
        sep=";",
    )
    df_hsk5 = pd.read_csv(
        "https://raw.githubusercontent.com/aurcode/chinese-words/main/%E5%90%AC%E5%8A%9B-hsk5-vocabulary",
        sep=";",
    )

    filters["hsk5"] = (
        pd.concat([df_ting, df_hsk5]).drop_duplicates(subset=["hanzi"]).reset_index(drop=True)
    )
    return filters


def analyze_word_extractor(
    *,
    uploaded_files: List[Tuple[str, bytes]],
    text_input: str,
    selected_hsk_levels: List[str],
    min_frequency: int,
) -> Dict[str, Any]:
    files_to_process: Dict[str, bytes] = {}

    for file_name, file_payload in uploaded_files:
        safe_name = sanitize_filename(file_name)
        validate_file_upload(
            _UploadProxy(safe_name, file_payload),
            expected_extensions=ALLOWED_WORD_EXTRACTOR_EXTENSIONS,
        )
        files_to_process[safe_name] = file_payload

    normalized_text = _safe_text(text_input)
    if normalized_text:
        key = "pasted_text.txt"
        if key in files_to_process:
            key = "__pasted_text_input__.txt"
        files_to_process[key] = normalized_text.encode("utf-8")

    if not files_to_process:
        raise ValueError("Upload at least one file or provide pasted text.")

    extractor = TextExtractor(files_to_process)
    extractor.extract_content()
    word_df = extractor.separated_chinese_characters()

    filtered_df = word_df.copy()
    removed_df = pd.DataFrame()

    normalized_levels = [str(level).strip().lower() for level in selected_hsk_levels if str(level).strip()]
    if normalized_levels and not word_df.empty:
        hsk_data = load_hsk_filters()
        filters_to_apply = {
            level: hsk_data[level]
            for level in normalized_levels
            if level in hsk_data
        }
        if filters_to_apply:
            filtered_df, removed_df = _filter_dataframe_hsk(
                word_df,
                filters_to_apply,
                filter_column_name="word",
            )

    safe_min_frequency = max(1, int(min_frequency or 1))
    if "frequency" in filtered_df.columns:
        final_df = filtered_df[filtered_df["frequency"] >= safe_min_frequency].copy()
    else:
        final_df = filtered_df.copy()

    word_list = "\n".join(final_df.get("word", pd.Series(dtype=str)).astype(str).tolist())

    return {
        "initial_words": _records_from_dataframe(word_df),
        "filtered_words": _records_from_dataframe(filtered_df),
        "removed_words": _records_from_dataframe(removed_df),
        "final_words": _records_from_dataframe(final_df),
        "copyable_word_list": word_list,
        "extraction_errors": dict(extractor.extraction_errors or {}),
        "summary": {
            "initial_count": int(len(word_df)),
            "filtered_count": int(len(filtered_df)),
            "removed_count": int(len(removed_df)),
            "final_count": int(len(final_df)),
            "min_frequency": safe_min_frequency,
            "applied_hsk_levels": normalized_levels,
        },
    }


def job_group_name(job_id: str) -> str:
    return f"{JOB_GROUP_PREFIX}{job_id}"


class BackgroundJobCanceledError(RuntimeError):
    pass


TERMINAL_BACKGROUND_JOB_STATUSES = {
    BackgroundJobStatus.SUCCESS,
    BackgroundJobStatus.ERROR,
    BackgroundJobStatus.CANCELED,
}


def serialize_background_job(job: BackgroundJob) -> Dict[str, Any]:
    return {
        "id": str(job.id),
        "job_type": job.job_type,
        "status": job.status,
        "progress_ratio": float(job.progress_ratio or 0.0),
        "status_text": job.status_text,
        "result_payload": dict(job.result_payload or {}),
        "csv_output_path": job.csv_output_path,
        "csv_download_name": job.csv_download_name,
        "celery_task_id": job.celery_task_id,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


def serialize_background_job_event(event: BackgroundJobEvent) -> Dict[str, Any]:
    payload = dict(event.payload or {})
    payload.setdefault("event", event.event_type)
    return {
        "id": event.id,
        "job_id": str(event.job_id),
        "sequence": event.sequence,
        "created_at": event.created_at.isoformat(),
        "payload": payload,
    }


def record_background_job_event(job_id: str, payload: Dict[str, Any]) -> BackgroundJobEvent:
    normalized_payload = dict(payload or {})
    event_type = str(normalized_payload.get("event", "unknown"))

    with transaction.atomic():
        job = BackgroundJob.objects.select_for_update().get(pk=job_id)
        sequence = int(job.last_event_sequence or 0) + 1
        job.last_event_sequence = sequence
        job.save(update_fields=["last_event_sequence", "updated_at"])
        event = BackgroundJobEvent.objects.create(
            job=job,
            sequence=sequence,
            event_type=event_type,
            payload=normalized_payload,
        )

    channel_layer = get_channel_layer()
    if channel_layer is not None:
        outbound = serialize_background_job_event(event)
        try:
            async_to_sync(channel_layer.group_send)(
                job_group_name(str(job_id)),
                {
                    "type": "background.job.event",
                    "payload": outbound,
                },
            )
        except Exception as exc:
            logger.warning(
                "Failed to send websocket event for background job {}: {}",
                job_id,
                exc,
            )
    return event


def _store_background_input_file(job_id: str, file_name: str, file_bytes: bytes) -> str:
    safe_name = sanitize_filename(file_name)
    target_dir = Path(settings.MEDIA_ROOT) / "job_inputs" / str(job_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / safe_name
    target_path.write_bytes(file_bytes)

    try:
        return str(target_path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except Exception:
        return target_path.as_posix()


def _resolve_workspace_path(path_value: str) -> Path:
    path = Path(path_value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    resolved = path.resolve()
    if PROJECT_ROOT.resolve() not in resolved.parents:
        raise ValueError("Path is outside workspace.")
    return resolved


def update_background_job_progress(
    *,
    job_id: str,
    progress_ratio: float,
    status_text: str,
) -> None:
    clamped_progress = max(0.0, min(1.0, float(progress_ratio)))
    BackgroundJob.objects.filter(pk=job_id).update(
        progress_ratio=clamped_progress,
        status_text=str(status_text or "")[:255],
        updated_at=timezone.now(),
    )


def resolve_background_job_csv_path(job: BackgroundJob) -> Path:
    if not str(job.csv_output_path or "").strip():
        raise ValueError("CSV output is not available for this job.")
    return _resolve_workspace_path(str(job.csv_output_path))


def list_background_jobs_for_owner(
    *,
    owner,
    job_type: Optional[str] = None,
    limit: int = 20,
) -> List[BackgroundJob]:
    safe_limit = max(1, min(int(limit or 20), 100))
    queryset = BackgroundJob.objects.filter(owner=owner)
    normalized_job_type = str(job_type or "").strip().lower()
    if normalized_job_type:
        queryset = queryset.filter(job_type=normalized_job_type)
    return list(queryset.order_by("-created_at")[:safe_limit])


def _clone_json_payload(payload: Any) -> Dict[str, Any]:
    try:
        raw = json.loads(json.dumps(payload or {}))
        if isinstance(raw, dict):
            return raw
    except Exception:
        pass
    return dict(payload or {})


def retry_background_job_for_owner(*, owner, job_id: str) -> BackgroundJob:
    original = BackgroundJob.objects.get(pk=job_id, owner=owner)
    if original.status not in {BackgroundJobStatus.ERROR, BackgroundJobStatus.CANCELED}:
        raise ValueError("Only failed or canceled jobs can be retried.")

    retried_job = BackgroundJob.objects.create(
        owner=owner,
        job_type=original.job_type,
        status=BackgroundJobStatus.QUEUED,
        input_payload=_clone_json_payload(original.input_payload),
    )
    record_background_job_event(
        str(retried_job.id),
        {
            "event": "job_queued",
            "job_type": retried_job.job_type,
            "retry_of_job_id": str(original.id),
        },
    )
    return retried_job


def cancel_background_job_for_owner(*, owner, job_id: str) -> BackgroundJob:
    with transaction.atomic():
        job = BackgroundJob.objects.select_for_update().get(pk=job_id, owner=owner)
        if job.status in TERMINAL_BACKGROUND_JOB_STATUSES:
            return job

        job.status = BackgroundJobStatus.CANCELED
        job.status_text = "Canceled by user."
        job.completed_at = timezone.now()
        job.error_message = "Canceled by user."
        job.save(
            update_fields=["status", "status_text", "completed_at", "error_message", "updated_at"]
        )

    record_background_job_event(
        str(job.id),
        {
            "event": "job_canceled",
            "job_type": job.job_type,
            "progress_ratio": float(job.progress_ratio or 0.0),
            "status_text": "Canceled by user.",
        },
    )
    return job


def _ensure_job_not_canceled(job_id: str) -> None:
    current_status = (
        BackgroundJob.objects.filter(pk=job_id).values_list("status", flat=True).first()
    )
    if current_status == BackgroundJobStatus.CANCELED:
        raise BackgroundJobCanceledError("Job canceled by user.")


def _persist_word_extractor_csv(job: BackgroundJob, result: Dict[str, Any]) -> Tuple[str, str]:
    output_dir = PROJECT_ROOT / "output" / "word_extractor"
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_file_name = f"word_extractor_{job.id}.csv"
    csv_path = output_dir / csv_file_name

    final_rows = result.get("final_words")
    if isinstance(final_rows, list):
        final_df = pd.DataFrame(final_rows)
    else:
        final_df = pd.DataFrame()

    final_df.to_csv(csv_path, index=False)
    try:
        csv_relative = str(csv_path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except Exception:
        csv_relative = csv_path.as_posix()
    return csv_relative, csv_file_name


def create_anki_background_job(
    *,
    owner,
    csv_name: str,
    csv_bytes: bytes,
    deck_name: str,
    config_payload: Dict[str, Any],
) -> BackgroundJob:
    safe_name = sanitize_filename(csv_name)
    validate_file_upload(_UploadProxy(safe_name, csv_bytes), expected_extensions=[".csv"])
    resolved_deck_name = _sanitize_deck_name(deck_name)

    job = BackgroundJob.objects.create(
        owner=owner,
        job_type=BackgroundJobType.ANKI_DECK,
        status=BackgroundJobStatus.QUEUED,
        progress_ratio=0.0,
        status_text="Queued",
        input_payload={},
    )

    csv_path = _store_background_input_file(str(job.id), safe_name, csv_bytes)
    job.input_payload = {
        "csv_name": safe_name,
        "csv_path": csv_path,
        "deck_name": resolved_deck_name,
        "config": dict(config_payload or {}),
    }
    job.save(update_fields=["input_payload", "updated_at"])
    record_background_job_event(
        str(job.id),
        {
            "event": "job_queued",
            "job_type": job.job_type,
            "progress_ratio": 0.0,
            "status_text": "Queued",
            "csv_name": safe_name,
            "deck_name": resolved_deck_name,
        },
    )
    return job


def create_word_extractor_background_job(
    *,
    owner,
    uploaded_files: List[Tuple[str, bytes]],
    text_input: str,
    selected_hsk_levels: List[str],
    min_frequency: int,
) -> BackgroundJob:
    normalized_levels = [str(level).strip().lower() for level in selected_hsk_levels if str(level).strip()]
    safe_min_frequency = max(1, int(min_frequency or 1))

    if not uploaded_files and not _safe_text(text_input):
        raise ValueError("Upload at least one file or provide pasted text.")

    job = BackgroundJob.objects.create(
        owner=owner,
        job_type=BackgroundJobType.WORD_EXTRACTOR,
        status=BackgroundJobStatus.QUEUED,
        progress_ratio=0.0,
        status_text="Queued",
        input_payload={},
    )

    stored_files: List[Dict[str, str]] = []
    for file_name, file_bytes in uploaded_files:
        safe_name = sanitize_filename(file_name)
        validate_file_upload(
            _UploadProxy(safe_name, file_bytes),
            expected_extensions=ALLOWED_WORD_EXTRACTOR_EXTENSIONS,
        )
        file_path = _store_background_input_file(str(job.id), safe_name, file_bytes)
        stored_files.append({"name": safe_name, "path": file_path})

    job.input_payload = {
        "files": stored_files,
        "text_input": _safe_text(text_input),
        "selected_hsk_levels": normalized_levels,
        "min_frequency": safe_min_frequency,
    }
    job.save(update_fields=["input_payload", "updated_at"])
    record_background_job_event(
        str(job.id),
        {
            "event": "job_queued",
            "job_type": job.job_type,
            "progress_ratio": 0.0,
            "status_text": "Queued",
            "file_count": len(stored_files),
            "has_text_input": bool(_safe_text(text_input)),
            "min_frequency": safe_min_frequency,
            "selected_hsk_levels": normalized_levels,
        },
    )
    return job


def run_anki_background_job(job_id: str) -> None:
    job = BackgroundJob.objects.get(pk=job_id, job_type=BackgroundJobType.ANKI_DECK)
    if job.status == BackgroundJobStatus.CANCELED:
        return

    job.status = BackgroundJobStatus.RUNNING
    job.progress_ratio = 0.05
    job.status_text = "Starting deck generation..."
    job.started_at = timezone.now()
    job.completed_at = None
    job.error_message = ""
    job.result_payload = {}
    job.csv_output_path = ""
    job.csv_download_name = ""
    job.last_event_sequence = 0
    job.save(
        update_fields=[
            "status",
            "progress_ratio",
            "status_text",
            "started_at",
            "completed_at",
            "error_message",
            "result_payload",
            "csv_output_path",
            "csv_download_name",
            "last_event_sequence",
            "updated_at",
        ]
    )
    BackgroundJobEvent.objects.filter(job=job).delete()
    record_background_job_event(
        str(job.id),
        {
            "event": "job_start",
            "job_type": job.job_type,
            "progress_ratio": 0.05,
            "status_text": "Starting deck generation...",
        },
    )

    try:
        payload = dict(job.input_payload or {})
        csv_path = _resolve_workspace_path(str(payload.get("csv_path", "")))
        csv_bytes = csv_path.read_bytes()
        _ensure_job_not_canceled(str(job.id))
        update_background_job_progress(
            job_id=str(job.id),
            progress_ratio=0.25,
            status_text="Loaded CSV input.",
        )
        record_background_job_event(
            str(job.id),
            {
                "event": "input_loaded",
                "csv_name": str(payload.get("csv_name", "")),
                "bytes": len(csv_bytes),
                "progress_ratio": 0.25,
                "status_text": "Loaded CSV input.",
            },
        )

        update_background_job_progress(
            job_id=str(job.id),
            progress_ratio=0.5,
            status_text="Generating Anki deck...",
        )
        artifact = generate_anki_deck_artifact(
            owner=job.owner,
            csv_name=str(payload.get("csv_name", "cards.csv")),
            csv_bytes=csv_bytes,
            deck_name=str(payload.get("deck_name", "My Anki Deck")),
            config_payload=dict(payload.get("config") or {}),
        )
        _ensure_job_not_canceled(str(job.id))
        update_background_job_progress(
            job_id=str(job.id),
            progress_ratio=0.9,
            status_text="Deck artifact generated.",
        )
        result_payload = {
            "artifact_id": str(artifact.id),
            "deck_name": artifact.deck_name,
            "source_csv_name": artifact.source_csv_name,
            "file_size_bytes": artifact.file_size_bytes,
            "output_path": artifact.output_path,
            "created_at": artifact.created_at.isoformat(),
        }

        job.status = BackgroundJobStatus.SUCCESS
        job.progress_ratio = 1.0
        job.status_text = "Completed successfully."
        job.completed_at = timezone.now()
        job.result_payload = result_payload
        job.save(
            update_fields=[
                "status",
                "progress_ratio",
                "status_text",
                "completed_at",
                "result_payload",
                "updated_at",
            ]
        )
        record_background_job_event(
            str(job.id),
            {
                "event": "job_complete",
                "job_type": job.job_type,
                "progress_ratio": 1.0,
                "status_text": "Completed successfully.",
                "result": result_payload,
            },
        )
    except BackgroundJobCanceledError:
        latest_job = BackgroundJob.objects.get(pk=job_id)
        if latest_job.status != BackgroundJobStatus.CANCELED:
            latest_job.status = BackgroundJobStatus.CANCELED
            latest_job.status_text = "Canceled by user."
            latest_job.completed_at = timezone.now()
            latest_job.error_message = "Canceled by user."
            latest_job.save(
                update_fields=[
                    "status",
                    "status_text",
                    "completed_at",
                    "error_message",
                    "updated_at",
                ]
            )
            record_background_job_event(
                str(latest_job.id),
                {
                    "event": "job_canceled",
                    "job_type": latest_job.job_type,
                    "progress_ratio": float(latest_job.progress_ratio or 0.0),
                    "status_text": "Canceled by user.",
                },
            )
        return
    except Exception as exc:
        job.status = BackgroundJobStatus.ERROR
        job.status_text = "Failed."
        job.completed_at = timezone.now()
        job.error_message = str(exc)
        job.save(
            update_fields=["status", "status_text", "completed_at", "error_message", "updated_at"]
        )
        record_background_job_event(
            str(job.id),
            {
                "event": "job_error",
                "job_type": job.job_type,
                "progress_ratio": float(job.progress_ratio or 0.0),
                "status_text": "Failed.",
                "error": str(exc),
            },
        )
        raise


def run_word_extractor_background_job(job_id: str) -> None:
    job = BackgroundJob.objects.get(pk=job_id, job_type=BackgroundJobType.WORD_EXTRACTOR)
    if job.status == BackgroundJobStatus.CANCELED:
        return

    job.status = BackgroundJobStatus.RUNNING
    job.progress_ratio = 0.05
    job.status_text = "Starting extraction..."
    job.started_at = timezone.now()
    job.completed_at = None
    job.error_message = ""
    job.result_payload = {}
    job.csv_output_path = ""
    job.csv_download_name = ""
    job.last_event_sequence = 0
    job.save(
        update_fields=[
            "status",
            "progress_ratio",
            "status_text",
            "started_at",
            "completed_at",
            "error_message",
            "result_payload",
            "csv_output_path",
            "csv_download_name",
            "last_event_sequence",
            "updated_at",
        ]
    )
    BackgroundJobEvent.objects.filter(job=job).delete()
    record_background_job_event(
        str(job.id),
        {
            "event": "job_start",
            "job_type": job.job_type,
            "progress_ratio": 0.05,
            "status_text": "Starting extraction...",
        },
    )

    try:
        payload = dict(job.input_payload or {})
        uploaded_files: List[Tuple[str, bytes]] = []
        for file_row in payload.get("files") or []:
            if not isinstance(file_row, dict):
                continue
            name = str(file_row.get("name", "")).strip()
            file_path = _resolve_workspace_path(str(file_row.get("path", "")))
            uploaded_files.append((name or file_path.name, file_path.read_bytes()))
        _ensure_job_not_canceled(str(job.id))
        update_background_job_progress(
            job_id=str(job.id),
            progress_ratio=0.2,
            status_text="Loaded input files.",
        )

        record_background_job_event(
            str(job.id),
            {
                "event": "input_loaded",
                "file_count": len(uploaded_files),
                "has_text_input": bool(_safe_text(payload.get("text_input"))),
                "progress_ratio": 0.2,
                "status_text": "Loaded input files.",
            },
        )

        update_background_job_progress(
            job_id=str(job.id),
            progress_ratio=0.6,
            status_text="Extracting and filtering words...",
        )
        result = analyze_word_extractor(
            uploaded_files=uploaded_files,
            text_input=str(payload.get("text_input", "")),
            selected_hsk_levels=list(payload.get("selected_hsk_levels") or []),
            min_frequency=int(payload.get("min_frequency", 2) or 2),
        )
        _ensure_job_not_canceled(str(job.id))

        update_background_job_progress(
            job_id=str(job.id),
            progress_ratio=0.85,
            status_text="Saving CSV output...",
        )
        csv_output_path, csv_download_name = _persist_word_extractor_csv(job, result)
        result = {
            **result,
            "csv_output_path": csv_output_path,
            "csv_download_name": csv_download_name,
        }
        job.status = BackgroundJobStatus.SUCCESS
        job.progress_ratio = 1.0
        job.status_text = "Completed successfully."
        job.completed_at = timezone.now()
        job.result_payload = result
        job.csv_output_path = csv_output_path
        job.csv_download_name = csv_download_name
        job.save(
            update_fields=[
                "status",
                "progress_ratio",
                "status_text",
                "completed_at",
                "result_payload",
                "csv_output_path",
                "csv_download_name",
                "updated_at",
            ]
        )
        record_background_job_event(
            str(job.id),
            {
                "event": "job_complete",
                "job_type": job.job_type,
                "progress_ratio": 1.0,
                "status_text": "Completed successfully.",
                "summary": dict(result.get("summary") or {}),
                "csv_download_name": csv_download_name,
            },
        )
    except BackgroundJobCanceledError:
        latest_job = BackgroundJob.objects.get(pk=job_id)
        if latest_job.status != BackgroundJobStatus.CANCELED:
            latest_job.status = BackgroundJobStatus.CANCELED
            latest_job.status_text = "Canceled by user."
            latest_job.completed_at = timezone.now()
            latest_job.error_message = "Canceled by user."
            latest_job.save(
                update_fields=[
                    "status",
                    "status_text",
                    "completed_at",
                    "error_message",
                    "updated_at",
                ]
            )
            record_background_job_event(
                str(latest_job.id),
                {
                    "event": "job_canceled",
                    "job_type": latest_job.job_type,
                    "progress_ratio": float(latest_job.progress_ratio or 0.0),
                    "status_text": "Canceled by user.",
                },
            )
        return
    except Exception as exc:
        job.status = BackgroundJobStatus.ERROR
        job.status_text = "Failed."
        job.completed_at = timezone.now()
        job.error_message = str(exc)
        job.save(
            update_fields=["status", "status_text", "completed_at", "error_message", "updated_at"]
        )
        record_background_job_event(
            str(job.id),
            {
                "event": "job_error",
                "job_type": job.job_type,
                "progress_ratio": float(job.progress_ratio or 0.0),
                "status_text": "Failed.",
                "error": str(exc),
            },
        )
        raise


def get_background_job_for_owner(*, owner, job_id: str) -> BackgroundJob:
    return BackgroundJob.objects.get(pk=job_id, owner=owner)


def get_background_job_events_for_owner(*, owner, job_id: str) -> List[Dict[str, Any]]:
    job = get_background_job_for_owner(owner=owner, job_id=job_id)
    events = BackgroundJobEvent.objects.filter(job=job).order_by("sequence")
    return [serialize_background_job_event(event) for event in events]
