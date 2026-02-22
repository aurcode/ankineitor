import json
import re
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from ankineitor.common.pipeline_result_store import (
    list_saved_csv_files_for_profile,
    list_saved_profiles,
)


UNIFIED_FLASHCARD_TEMPLATE_COLUMNS = [
    "word",
    "categories",
    "pinyin",
    "translation",
    "audio",
    "timestamp",
    "word_model",
    "profile_id",
    "profile_version",
    "word_with_stress",
    "romanization",
    "pinyin_llm",
    "part_of_speech",
    "character_breakdown",
    "aspect_pair",
    "register",
    "grammar_formula",
    "detailed_explanation_english",
    "detailed_explanation_spanish",
    "meaning_english",
    "meaning_spanish",
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
    "translation_llm",
    "example_sentences",
    "improved_meaning",
    "sentence_1",
    "sentence_1_tts_clean",
    "sentence_1_cloze",
    "sentence_1_pinyin",
    "sentence_1_romanization",
    "sentence_1_translation_english",
    "sentence_1_translation_spanish",
    "sentence_1_audio",
    "sentence_2",
    "sentence_2_tts_clean",
    "sentence_2_cloze",
    "sentence_2_pinyin",
    "sentence_2_romanization",
    "sentence_2_translation_english",
    "sentence_2_translation_spanish",
    "sentence_2_audio",
    "sentence_3",
    "sentence_3_tts_clean",
    "sentence_3_cloze",
    "sentence_3_pinyin",
    "sentence_3_romanization",
    "sentence_3_translation_english",
    "sentence_3_translation_spanish",
    "sentence_3_audio",
    "sentence_4",
    "sentence_4_tts_clean",
    "sentence_4_cloze",
    "sentence_4_pinyin",
    "sentence_4_romanization",
    "sentence_4_translation_english",
    "sentence_4_translation_spanish",
    "sentence_4_audio",
    "image_term_type",
    "visual_description",
    "master_image_prompt",
    "image_generation_skip_reason",
    "picture",
    "image_render_status",
    "image_render_skip_reason",
]

INDEX_KEY = "flashcard_review_index"
SHOW_BACK_KEY = "flashcard_review_show_back"
DATASET_KEY = "flashcard_review_dataset_signature"
SOURCE_KEY = "flashcard_review_source"
SAVED_PROFILE_KEY = "flashcard_review_saved_profile"
SAVED_FILE_KEY = "flashcard_review_saved_file"
PROFILE_FILTER_KEY = "flashcard_review_profile_filter"


def _clean_col_name(col: Any) -> str:
    return str(col).replace("\ufeff", "").strip()


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


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
        fenced = re.match(
            r"^\s*```(?:json|JSON)?\s*(.*?)\s*```\s*$",
            stripped,
            flags=re.DOTALL,
        )
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


def _is_complex_json(value: Any) -> bool:
    if isinstance(value, dict):
        return True
    if isinstance(value, list):
        return any(isinstance(item, (dict, list)) for item in value)
    return False


def _render_collapsible_text(label: str, text: str, preview_chars: int = 240) -> None:
    value = _safe_text(text)
    if not value:
        return
    if len(value) <= preview_chars:
        st.markdown(f"**{label}:** {value}")
        return

    preview = value[:preview_chars].rstrip() + "..."
    escaped_label = escape(label)
    escaped_value = escape(value)
    st.markdown(f"**{label}:** {preview}")
    st.markdown(
        (
            f"<details><summary>Show full {escaped_label}</summary>"
            f"<pre style='white-space: pre-wrap; margin: 0.5rem 0 0;'>{escaped_value}</pre>"
            "</details>"
        ),
        unsafe_allow_html=True,
    )


def _parse_json_list(raw_value: Any) -> List[str]:
    parsed = _try_parse_json(raw_value)
    if isinstance(parsed, list):
        normalized = [_json_item_to_text(item) for item in parsed]
        return [value for value in normalized if value]
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


def _display_local_or_remote_audio(audio_path: str) -> None:
    value = _safe_text(audio_path)
    if not value:
        return

    if value.startswith(("http://", "https://")):
        st.audio(value)
        return

    path = Path(value)
    if path.exists() and path.is_file():
        st.audio(str(path))
    else:
        st.caption(f"Audio path: `{value}`")


def _display_image(picture_path: str) -> None:
    value = _safe_text(picture_path)
    if not value:
        return

    if value.startswith(("http://", "https://")):
        st.image(value, use_container_width=True)
        return

    path = Path(value)
    if path.exists() and path.is_file():
        st.image(str(path), use_container_width=True)
    else:
        st.caption(f"Image path: `{value}`")


def _format_saved_csv_option(file_path_value: str) -> str:
    file_path = Path(file_path_value)
    try:
        modified = datetime.fromtimestamp(file_path.stat().st_mtime).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    except OSError:
        modified = "unknown time"
    return f"{file_path.name} ({modified})"


def _render_front_card(row: pd.Series, index: int, total: int) -> None:
    word = _first_non_empty(row, ["word_with_stress", "word_model", "word"]) or "(no word)"
    pronunciation = _first_non_empty(row, ["pinyin_llm", "pinyin", "romanization"])
    part_of_speech = _safe_text(row.get("part_of_speech"))
    register = _safe_text(row.get("register"))
    profile = _safe_text(row.get("profile_id"))
    timestamp = _safe_text(row.get("timestamp"))

    metadata_parts: List[str] = []
    if part_of_speech:
        metadata_parts.append(f"POS: {escape(part_of_speech)}")
    if register:
        metadata_parts.append(f"Register: {escape(register)}")
    if profile:
        metadata_parts.append(f"Profile: {escape(profile)}")
    if timestamp:
        metadata_parts.append(f"Created: {escape(timestamp)}")
    metadata_html = " | ".join(metadata_parts)

    st.markdown(
        f"""
        <div style="border:1px solid #d1d5db;border-radius:14px;padding:24px;background:#fafafa;">
          <div style="font-size:12px;color:#6b7280;">Card {index + 1} of {total}</div>
          <div style="font-size:44px;font-weight:700;line-height:1.1;margin-top:8px;">{escape(word)}</div>
          <div style="font-size:20px;color:#1f2937;margin-top:8px;">{escape(pronunciation) if pronunciation else ""}</div>
          <div style="font-size:14px;color:#4b5563;margin-top:14px;">{metadata_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("#### Word Audio")
    _display_local_or_remote_audio(_safe_text(row.get("audio")))


def _render_meanings(row: pd.Series) -> None:
    with st.expander("Meanings", expanded=True):
        meaning_en = _first_non_empty(
            row,
            [
                "meaning_english",
                "detailed_explanation_english",
                "translation_llm",
                "translation",
            ],
        )
        meaning_es = _first_non_empty(
            row,
            ["meaning_spanish", "detailed_explanation_spanish"],
        )
        if meaning_en:
            _render_collapsible_text("EN", meaning_en, preview_chars=280)
        if meaning_es:
            _render_collapsible_text("ES", meaning_es, preview_chars=280)
        if not meaning_en and not meaning_es:
            st.caption("No meaning fields found for this card.")


def _render_details(row: pd.Series) -> None:
    with st.expander("Details", expanded=False):
        pairs = [
            ("Part of speech", "part_of_speech"),
            ("Register", "register"),
            ("Aspect pair", "aspect_pair"),
            ("Grammar formula", "grammar_formula"),
            ("Character/Morphological breakdown", "character_breakdown"),
            ("Mnemonic (ES)", "mnemonic_hook_spanish"),
            ("Piter summer variant", "piter_summer_variant"),
            ("Edge case notes", "edge_case_notes"),
            ("Improved meaning", "improved_meaning"),
            ("Example sentences", "example_sentences"),
            ("Categories", "categories"),
            ("Profile version", "profile_version"),
        ]
        has_any_details = False
        for label, key in pairs:
            value = _safe_text(row.get(key))
            if value:
                has_any_details = True
                _render_collapsible_text(label, value)
        if not has_any_details:
            st.caption("No extra detail fields found.")


def _render_relationships(row: pd.Series) -> None:
    with st.expander("Relationships (Parsed JSON)", expanded=False):
        relation_specs = [
            ("Synonyms", "synonyms_json", "synonyms_rendered"),
            ("Antonyms", "antonyms_json", "antonyms_rendered"),
            ("Collocations", "collocations_json", "collocations_rendered"),
        ]
        has_relationships = False

        for label, json_col, rendered_col in relation_specs:
            values = _list_from_columns(row, json_col, rendered_col)
            parsed_json = _try_parse_json(row.get(json_col))
            rendered_fallback = _safe_text(row.get(rendered_col))

            if values:
                has_relationships = True
                if len(values) <= 8 and all(len(value) < 140 for value in values):
                    st.markdown(f"**{label}:** " + " | ".join(values))
                else:
                    st.markdown(f"**{label}:**")
                    for index, value in enumerate(values, start=1):
                        _render_collapsible_text(f"{label} {index}", value, preview_chars=220)

            if (
                isinstance(parsed_json, (dict, list))
                and parsed_json
                and _is_complex_json(parsed_json)
            ):
                has_relationships = True
                st.caption(f"Parsed `{json_col}`:")
                st.json(parsed_json)
            elif not values and rendered_fallback:
                has_relationships = True
                _render_collapsible_text(label, rendered_fallback, preview_chars=220)

        if not has_relationships:
            st.caption("No relationships found.")


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
                "translation_english": _safe_text(
                    row.get(f"sentence_{idx}_translation_english")
                ),
                "translation_spanish": _safe_text(
                    row.get(f"sentence_{idx}_translation_spanish")
                ),
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
            entries.append(
                {
                    "index": str(idx),
                    "sentence": _first_non_empty(
                        pd.Series(item),
                        ["target_language_highlighted", "sentence", "text"],
                    ),
                    "tts_clean": _safe_text(item.get("tts_clean_sentence")),
                    "cloze": _safe_text(item.get("target_language_cloze")),
                    "pronunciation": _first_non_empty(
                        pd.Series(item),
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


def _render_sentences(row: pd.Series) -> None:
    with st.expander("Sentences (Parsed)", expanded=False):
        entries = _sentence_entries_from_columns(row)
        if not entries:
            entries = _sentence_entries_from_json(row)

        if entries:
            for entry in entries:
                st.markdown(f"**Sentence {entry['index']}**")
                if entry["sentence"]:
                    st.markdown(entry["sentence"], unsafe_allow_html=True)
                if entry["tts_clean"]:
                    _render_collapsible_text(
                        "TTS clean", entry["tts_clean"], preview_chars=220
                    )
                if entry["cloze"]:
                    _render_collapsible_text("Cloze", entry["cloze"], preview_chars=220)
                if entry["pronunciation"]:
                    _render_collapsible_text(
                        "Pronunciation", entry["pronunciation"], preview_chars=220
                    )
                if entry["translation_english"]:
                    _render_collapsible_text(
                        "EN", entry["translation_english"], preview_chars=260
                    )
                if entry["translation_spanish"]:
                    _render_collapsible_text(
                        "ES", entry["translation_spanish"], preview_chars=260
                    )
                _display_local_or_remote_audio(entry["audio"])
                st.divider()
        else:
            rendered_html = _safe_text(row.get("sentences_rendered_html"))
            if rendered_html:
                st.markdown(rendered_html, unsafe_allow_html=True)
            else:
                st.caption("No sentence fields found.")

        parsed_sentences_json = _try_parse_json(row.get("sentences_json"))
        raw_sentences_json = _safe_text(row.get("sentences_json"))
        if isinstance(parsed_sentences_json, (dict, list)) and parsed_sentences_json:
            st.caption("Parsed `sentences_json`:")
            st.json(parsed_sentences_json)
        elif raw_sentences_json:
            _render_collapsible_text("sentences_json", raw_sentences_json, preview_chars=220)


def _render_image_section(row: pd.Series) -> None:
    with st.expander("Image & Prompt Metadata", expanded=False):
        _display_image(_safe_text(row.get("picture")))

        metadata_pairs = [
            ("Type", "image_term_type"),
            ("Visual description", "visual_description"),
            ("Master prompt", "master_image_prompt"),
            ("Generation skip reason", "image_generation_skip_reason"),
            ("Render status", "image_render_status"),
            ("Render skip reason", "image_render_skip_reason"),
        ]
        has_metadata = False
        for label, key in metadata_pairs:
            value = _safe_text(row.get(key))
            if value:
                has_metadata = True
                _render_collapsible_text(label, value, preview_chars=220)
        if not has_metadata:
            st.caption("No image metadata found.")


def _render_raw_json_fields(row: pd.Series) -> None:
    json_columns = [str(column) for column in row.index if str(column).endswith("_json")]
    with st.expander("Raw JSON Columns", expanded=False):
        has_json = False
        for column_name in json_columns:
            raw_value = _safe_text(row.get(column_name))
            if not raw_value:
                continue
            has_json = True
            st.markdown(f"**{column_name}**")
            parsed_value = _try_parse_json(raw_value)
            if isinstance(parsed_value, (dict, list)):
                st.json(parsed_value)
            else:
                _render_collapsible_text(column_name, raw_value, preview_chars=220)
        if not has_json:
            st.caption("No populated JSON columns in this card.")


def _render_profile_summary(df: pd.DataFrame) -> None:
    if "profile_id" not in df.columns:
        return
    profile_counts = (
        df["profile_id"]
        .astype(str)
        .str.strip()
        .replace("", pd.NA)
        .dropna()
        .value_counts()
        .reset_index()
    )
    if profile_counts.empty:
        return
    profile_counts.columns = ["profile_id", "cards"]
    with st.expander("Profile distribution"):
        st.dataframe(profile_counts, use_container_width=True, hide_index=True)


def _load_dataframe_from_source() -> tuple[pd.DataFrame, str, int]:
    saved_profiles = list_saved_profiles()
    source_options = ["Upload CSV"]
    if saved_profiles:
        source_options.insert(0, "Saved Pipeline CSV")
    else:
        st.caption(
            "No saved pipeline CSVs found yet. Run the pipeline first to create them."
        )

    if st.session_state.get(SOURCE_KEY) not in source_options:
        st.session_state[SOURCE_KEY] = source_options[0]

    source = st.radio(
        "CSV Source",
        options=source_options,
        horizontal=True,
        key=SOURCE_KEY,
    )

    if source == "Saved Pipeline CSV":
        if st.session_state.get(SAVED_PROFILE_KEY) not in saved_profiles:
            st.session_state[SAVED_PROFILE_KEY] = saved_profiles[0]
        selected_profile = st.selectbox(
            "Profile",
            options=saved_profiles,
            key=SAVED_PROFILE_KEY,
        )
        saved_files = list_saved_csv_files_for_profile(selected_profile)
        if not saved_files:
            st.warning(f"No saved CSV files found for profile `{selected_profile}`.")
            st.stop()

        saved_file_options = [file_path.as_posix() for file_path in saved_files]
        if st.session_state.get(SAVED_FILE_KEY) not in saved_file_options:
            st.session_state[SAVED_FILE_KEY] = saved_file_options[0]

        selected_file = st.selectbox(
            "Saved CSV",
            options=saved_file_options,
            format_func=_format_saved_csv_option,
            key=SAVED_FILE_KEY,
        )
        selected_path = Path(selected_file)
        try:
            loaded_df = pd.read_csv(selected_path, low_memory=False)
        except Exception as exc:
            st.error(f"Could not read saved CSV: {exc}")
            st.stop()

        try:
            source_size = int(selected_path.stat().st_size)
        except OSError:
            source_size = 0
        return loaded_df, selected_path.as_posix(), source_size

    uploaded = st.file_uploader(
        "Upload flashcards CSV",
        type=["csv"],
        key="flashcard_review_csv_uploader",
        accept_multiple_files=False,
    )
    if not uploaded:
        st.stop()

    try:
        uploaded.seek(0)
        loaded_df = pd.read_csv(uploaded, low_memory=False)
    except Exception as exc:
        st.error(f"Could not read CSV: {exc}")
        st.stop()
    return loaded_df, uploaded.name, int(uploaded.size)


def render_csv_flashcards_tab() -> None:
    st.header("CSV Flashcard Reviewer")
    st.markdown(
        "Single reviewer for all profiles. Select a saved pipeline CSV (per profile) "
        "or upload your own CSV."
    )

    template_bytes = (
        pd.DataFrame(columns=UNIFIED_FLASHCARD_TEMPLATE_COLUMNS)
        .to_csv(index=False)
        .encode("utf-8-sig")
    )
    st.download_button(
        "Download Unified CSV Template",
        data=template_bytes,
        file_name="flashcards_template_unified.csv",
        mime="text/csv",
        use_container_width=True,
    )

    df, source_name, source_size = _load_dataframe_from_source()

    df.columns = [_clean_col_name(col) for col in df.columns]
    df = df.astype(object).where(pd.notnull(df), None)

    if df.empty:
        st.warning("The selected CSV has no rows.")
        return

    profile_filter_value = "All profiles"
    if "profile_id" in df.columns:
        profile_values = (
            df["profile_id"]
            .astype(str)
            .str.strip()
            .replace("", pd.NA)
            .dropna()
            .unique()
            .tolist()
        )
        profile_values = sorted(profile_values)
        if profile_values:
            profile_options = ["All profiles"] + profile_values
            if st.session_state.get(PROFILE_FILTER_KEY) not in profile_options:
                st.session_state[PROFILE_FILTER_KEY] = "All profiles"
            profile_filter_value = st.selectbox(
                "Profile Filter",
                options=profile_options,
                key=PROFILE_FILTER_KEY,
            )
            if profile_filter_value != "All profiles":
                df = (
                    df[df["profile_id"].astype(str).str.strip() == profile_filter_value]
                    .copy()
                    .reset_index(drop=True)
                )

    if df.empty:
        st.warning("No cards available for the selected profile filter.")
        return

    word_columns = [col for col in ["word_with_stress", "word_model", "word"] if col in df.columns]
    if not word_columns:
        st.warning(
            "CSV has no `word_with_stress`, `word_model`, or `word` column. "
            "Card front may appear empty."
        )

    st.caption(f"Loaded `{source_name}` with {len(df)} flashcards.")
    _render_profile_summary(df)

    dataset_signature = (
        f"{source_name}:{source_size}:{profile_filter_value}:{len(df)}"
    )
    if st.session_state.get(DATASET_KEY) != dataset_signature:
        st.session_state[DATASET_KEY] = dataset_signature
        st.session_state[INDEX_KEY] = 0
        st.session_state[SHOW_BACK_KEY] = False

    if INDEX_KEY not in st.session_state:
        st.session_state[INDEX_KEY] = 0
    if SHOW_BACK_KEY not in st.session_state:
        st.session_state[SHOW_BACK_KEY] = False

    total = len(df)
    current_index = int(st.session_state[INDEX_KEY])
    current_index = max(0, min(current_index, total - 1))
    st.session_state[INDEX_KEY] = current_index

    nav_col1, nav_col2, nav_col3, nav_col4 = st.columns([1, 2, 1, 1])
    with nav_col1:
        if st.button("⬅ Previous", use_container_width=True, disabled=current_index == 0):
            st.session_state[INDEX_KEY] = current_index - 1
            st.session_state[SHOW_BACK_KEY] = False
            st.rerun()
    with nav_col2:
        if total > 1:
            selected_card = st.slider(
                "Card",
                min_value=1,
                max_value=total,
                value=current_index + 1,
                key="flashcard_slider",
            )
            if selected_card - 1 != current_index:
                st.session_state[INDEX_KEY] = selected_card - 1
                st.session_state[SHOW_BACK_KEY] = False
                st.rerun()
        else:
            st.caption("Card 1 of 1")
    with nav_col3:
        if st.button("Next ➡", use_container_width=True, disabled=current_index >= total - 1):
            st.session_state[INDEX_KEY] = current_index + 1
            st.session_state[SHOW_BACK_KEY] = False
            st.rerun()
    with nav_col4:
        if st.button("Flip Card", use_container_width=True, key="flashcard_flip"):
            st.session_state[SHOW_BACK_KEY] = not bool(st.session_state[SHOW_BACK_KEY])
            st.rerun()

    row = df.iloc[st.session_state[INDEX_KEY]]
    if not bool(st.session_state[SHOW_BACK_KEY]):
        _render_front_card(row=row, index=st.session_state[INDEX_KEY], total=total)
    else:
        _render_meanings(row=row)
        _render_details(row=row)
        _render_relationships(row=row)
        _render_sentences(row=row)
        _render_image_section(row=row)
        _render_raw_json_fields(row=row)
