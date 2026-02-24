from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from pipeline_api.tab_services import (
    GENERATED_ROW_RERUN_PROCESSES,
    _columns_to_replace_for_generated_rerun,
    _rerun_process_dataframe_without_cache,
)


def test_audio_sentences_rerun_includes_llm_sentence_stage():
    assert GENERATED_ROW_RERUN_PROCESSES["audio_sentences"] == [
        "LLM (Meanings/Sentences)",
        "LLM Audio (Sentences)",
    ]


def test_audio_sentences_column_replacement_includes_existing_audio_columns():
    generated_row = {
        "word": "你好",
        "sentence_1_audio": "./my_audio_files/new-1.mp3",
    }
    current_row = {
        "word": "你好",
        "sentence_1_audio": "./my_audio_files/old-1.mp3",
        "sentence_2_audio": "./my_audio_files/old-2.mp3",
    }

    columns = _columns_to_replace_for_generated_rerun(
        process="audio_sentences",
        generated_row=generated_row,
        current_row=current_row,
    )

    assert columns == {"sentence_1_audio", "sentence_2_audio"}


def test_rerun_dataframe_without_cache_applies_only_requested_transforms():
    class _AudioTransform:
        def __init__(self):
            self.calls = 0

        def apply(self, df: pd.DataFrame) -> pd.DataFrame:
            self.calls += 1
            out = df.copy()
            out["audio"] = out["word"].astype(str).map(lambda word: f"A:{word}")
            return out

    class _SentenceAudioTransform:
        def __init__(self):
            self.calls = 0

        def apply(self, df: pd.DataFrame) -> pd.DataFrame:
            self.calls += 1
            out = df.copy()
            out["sentence_1_audio"] = out["word"].astype(str).map(lambda word: f"S:{word}")
            return out

    audio_transform = _AudioTransform()
    sentence_transform = _SentenceAudioTransform()
    prepared_run = SimpleNamespace(
        ordered_transform_names=["Audio", "LLM Audio (Sentences)"],
        selected_transforms=[audio_transform, sentence_transform],
    )

    rerun_df = _rerun_process_dataframe_without_cache(
        prepared_run=prepared_run,
        word="你好",
        transform_names=["Audio"],
    )

    assert audio_transform.calls == 1
    assert sentence_transform.calls == 0
    assert rerun_df.loc[0, "audio"] == "A:你好"


def test_rerun_dataframe_without_cache_seeds_existing_row_values():
    class _InspectorTransform:
        def __init__(self):
            self.input_df = None

        def apply(self, df: pd.DataFrame) -> pd.DataFrame:
            self.input_df = df.copy()
            return df.copy()

    inspector = _InspectorTransform()
    prepared_run = SimpleNamespace(
        ordered_transform_names=["LLM Audio (Sentences)"],
        selected_transforms=[inspector],
    )

    rerun_df = _rerun_process_dataframe_without_cache(
        prepared_run=prepared_run,
        word="hola",
        transform_names=["LLM Audio (Sentences)"],
        seed_row={
            "sentence_1": "Hola.",
            "sentence_1_audio": "./my_audio_files/existing.mp3",
        },
    )

    assert inspector.input_df is not None
    assert inspector.input_df.loc[0, "word"] == "hola"
    assert inspector.input_df.loc[0, "sentence_1_audio"] == "./my_audio_files/existing.mp3"
    assert rerun_df.loc[0, "sentence_1_audio"] == "./my_audio_files/existing.mp3"
