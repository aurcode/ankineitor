from __future__ import annotations

import importlib
import io
import json
import re
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import yaml
from django.conf import settings

from ankineitor.common.pipeline_result_store import (
    list_saved_csv_files_for_profile,
    list_saved_profiles,
)
from ankineitor.pipeline.text_extractor import TextExtractor
from ankineitor.security import sanitize_filename, validate_file_upload
from ankineitor.security.exceptions import InvalidFileError, ValidationError

from .models import (
    FlashcardDataset,
    FlashcardDatasetSourceType,
    GeneratedAnkiDeck,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ALLOWED_WORD_EXTRACTOR_EXTENSIONS = [".pdf", ".docx", ".txt", ".pptx"]
SAFE_DECK_NAME_PATTERN = re.compile(r"^[A-Za-z0-9 _\-]{2,120}$")


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()


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
    return list_saved_profiles()


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


def _load_dataset_dataframe(dataset: FlashcardDataset) -> pd.DataFrame:
    csv_path = Path(dataset.csv_path)
    if not csv_path.is_absolute():
        csv_path = PROJECT_ROOT / csv_path
    csv_path = csv_path.resolve()
    stats = csv_path.stat()
    cached = _load_dataset_cache(csv_path.as_posix(), int(stats.st_mtime_ns), int(stats.st_size))
    return cached.copy()


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
        source_type=FlashcardDatasetSourceType.SAVED,
        source_label=f"{profile_id}:{selected_path.name}",
        csv_path=csv_relative,
        total_cards=int(len(df)),
        columns=list(df.columns),
    )
    return _dataset_summary_payload(dataset, df)


def create_flashcard_dataset_from_upload(*, file_name: str, file_bytes: bytes) -> Dict[str, Any]:
    safe_name = sanitize_filename(file_name)
    validate_file_upload(_UploadProxy(safe_name, file_bytes), expected_extensions=[".csv"])

    df = _read_dataset_csv_bytes(file_bytes)
    if df.empty:
        raise ValueError("Uploaded CSV is empty.")

    upload_dir = Path(settings.MEDIA_ROOT) / "flashcard_uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    dataset_id = FlashcardDataset.objects.create(
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


def get_flashcard_dataset_summary(dataset_id: str) -> Dict[str, Any]:
    dataset = FlashcardDataset.objects.get(pk=dataset_id)
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
                    [f"sentence_{idx}_pinyin", f"sentence_{idx}_romanization"],
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
                        ["sentence_pinyin", "sentence_romanization", "romanization"],
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
        "aspect_pair": _safe_text(row.get("aspect_pair")),
        "grammar_formula": _safe_text(row.get("grammar_formula")),
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
    index: int,
    profile_filter: Optional[str],
) -> Dict[str, Any]:
    dataset = FlashcardDataset.objects.get(pk=dataset_id)
    df = _load_dataset_dataframe(dataset)

    normalized_filter = _safe_text(profile_filter)
    if normalized_filter and normalized_filter != "All profiles" and "profile_id" in df.columns:
        df = (
            df[df["profile_id"].astype(str).str.strip() == normalized_filter]
            .copy()
            .reset_index(drop=True)
        )

    if df.empty:
        raise ValueError("No cards available for this dataset/filter.")

    safe_index = max(0, min(int(index), len(df) - 1))
    row = df.iloc[safe_index]
    return _build_flashcard_card_payload(row=row, index=safe_index, total=len(df))


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
