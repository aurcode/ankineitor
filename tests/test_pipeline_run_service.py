"""Unit tests for application-level pipeline orchestration service."""

from typing import Any, Dict
import time

import pandas as pd
import pytest

from ankineitor.application.pipeline_run_service import PipelineRunService
from ankineitor.common import pipeline_result_store as result_store
from ankineitor.pipeline.llm_image_prompt_transformation import (
    LLMImagePromptTransformation,
)
from ankineitor.pipeline.llm_image_transformation import LLMImageTransformation
from ankineitor.pipeline.llm_profiles import LLMProfile
from ankineitor.pipeline.transformations import Transformation


class _FakePipelineDBClient:
    def __init__(self):
        self.rows: Dict[str, Dict[str, Any]] = {}

    def find_many_by_field(self, keys, table_name, field_name):
        del table_name, field_name
        return [self.rows[str(key)] for key in keys if str(key) in self.rows]

    def insert_many_records(self, records, table_name):
        del table_name
        for record in records:
            self.rows[str(record["word"])] = dict(record)

    def insert_many_records_missing_fields(self, records, columns, table_name, field_name):
        del columns, table_name, field_name
        for record in records:
            self.rows[str(record["word"])] = dict(record)

    def add_category(self, key, new_category, table_name="hanzi_processing", field_name="word"):
        del table_name, field_name
        row = self.rows.setdefault(str(key), {"word": str(key), "categories": []})
        categories = row.get("categories") or []
        if new_category not in categories:
            categories.append(new_category)
        row["categories"] = categories

    def get_categories_by_word(self, key, table_name="hanzi_processing"):
        del table_name
        row = self.rows.get(str(key), {})
        return list(row.get("categories") or [])


class _DummyTranslationTransform(Transformation):
    @property
    def column_name(self) -> str:
        return "translation"

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        output = df.copy()
        output["translation"] = output["word"].astype(str).map(lambda word: f"T:{word}")
        return output


class _SourceAwareDummyTransform(Transformation):
    def __init__(self, source_language: str):
        self.source_language = source_language

    @property
    def column_name(self) -> str:
        return "debug_source"

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        output = df.copy()
        output["debug_source"] = self.source_language
        return output


class _DummyTimestampTransform(Transformation):
    @property
    def column_name(self) -> str:
        return "timestamp"

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        output = df.copy()
        output["timestamp"] = "2026-02-22"
        return output


class _DummyAudioTransform(Transformation):
    @property
    def column_name(self) -> str:
        return "audio"

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        output = df.copy()
        output["audio"] = output["word"].astype(str).map(lambda word: f"A:{word}")
        return output


class _DummyLlmMeaningTransform(Transformation):
    pipeline_stage = "llm"

    @property
    def column_name(self) -> str:
        return "sentence_1"

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        output = df.copy()
        output["sentence_1"] = output["word"].astype(str).map(lambda word: f"S:{word}")
        return output


class _DummyLlmAudioTransform(Transformation):
    pipeline_stage = "llm"
    required_input_columns = ("sentence_1",)

    @property
    def column_name(self) -> str:
        return "sentence_1_audio"

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        output = df.copy()
        output["sentence_1_audio"] = output["sentence_1"].astype(str).map(
            lambda sentence: f"A:{sentence}"
        )
        return output


class _DummyImagePromptTransform(Transformation):
    pipeline_stage = "llm"

    @property
    def column_name(self) -> str:
        return "master_image_prompt"

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        output = df.copy()
        output["master_image_prompt"] = output["word"].astype(str).map(
            lambda word: f"P:{word}"
        )
        return output


class _DummyImageRendererTransform(Transformation):
    pipeline_stage = "llm"
    required_input_columns = ("master_image_prompt",)

    @property
    def column_name(self) -> str:
        return "image"

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        # Keep this transform slow to validate pipeline overlap between words.
        time.sleep(0.05)
        output = df.copy()
        output["image"] = output["master_image_prompt"].astype(str).map(
            lambda prompt: f"I:{prompt}"
        )
        return output


def _build_test_profile(*, supports_images: bool) -> LLMProfile:
    return LLMProfile(
        profile_id="test_profile",
        display_name="Test Profile",
        description="Profile used for service unit tests.",
        source_language="Chinese (Simplified)",
        sentence_language="Simplified Chinese",
        secondary_target_language="Spanish",
        supports_images=supports_images,
        prompt_template="word={word}",
        prompt_version="test-v1",
        response_schema="test_schema_v1",
    )


def test_build_ordered_transform_names_deduplicates_and_preserves_order():
    service = PipelineRunService()
    all_transformations = {"A": object(), "B": object(), "C": object()}

    ordered = service.build_ordered_transform_names(
        all_transformations=all_transformations,
        always_included_transform_names=["B", "A"],
        selected_transform_names=["A", "C", "B", "C"],
    )

    assert ordered == ["B", "A", "C"]


def test_build_ordered_transform_names_moves_image_prompt_before_renderer():
    service = PipelineRunService()
    image_prompt = object.__new__(LLMImagePromptTransformation)
    image_renderer = object.__new__(LLMImageTransformation)
    all_transformations = {
        "LLM Image Renderer (Master Prompt)": image_renderer,
        "LLM Image Prompt (Visual Translator)": image_prompt,
    }

    ordered = service.build_ordered_transform_names(
        all_transformations=all_transformations,
        always_included_transform_names=[],
        selected_transform_names=[
            "LLM Image Renderer (Master Prompt)",
            "LLM Image Prompt (Visual Translator)",
        ],
    )

    assert ordered == [
        "LLM Image Prompt (Visual Translator)",
        "LLM Image Renderer (Master Prompt)",
    ]


def test_prepare_pipeline_run_raises_when_runtime_factory_misses_transform():
    service = PipelineRunService()
    db_client = _FakePipelineDBClient()
    all_transforms = {"translate": _DummyTranslationTransform()}

    def _factory_missing_required():
        return {}

    with pytest.raises(ValueError, match=r"(?i)missing configured transform"):
        service.prepare_pipeline_run(
            pipeline_db_client=db_client,
            all_transformations=all_transforms,
            ordered_transform_names=["translate"],
            llm_profile_id="lotm_zh_en_es",
            llm_source_language="Chinese (Simplified)",
            transform_factory=_factory_missing_required,
        )


def test_execute_pipeline_run_persists_results_csv(tmp_path, monkeypatch):
    service = PipelineRunService()
    db_client = _FakePipelineDBClient()
    all_transforms = {"translate": _DummyTranslationTransform()}
    monkeypatch.setattr(result_store, "PIPELINE_RESULTS_ROOT", tmp_path / "results")
    progress_events = []

    prepared = service.prepare_pipeline_run(
        pipeline_db_client=db_client,
        all_transformations=all_transforms,
        ordered_transform_names=["translate"],
        llm_profile_id="lotm_zh_en_es",
        llm_source_language="Chinese (Simplified)",
    )

    run_result = service.execute_pipeline_run(
        prepared_run=prepared,
        words=["hola", "adios"],
        llm_profile_id="lotm_zh_en_es",
        progress_callback=progress_events.append,
    )

    assert set(run_result.df_results["word"]) == {"hola", "adios"}
    assert "translation" in run_result.df_results.columns
    assert run_result.saved_results_csv.exists()
    assert run_result.saved_results_csv.parent == tmp_path / "results" / "lotm_zh_en_es"

    transform_start = next(
        event for event in progress_events if event.get("event") == "transform_start"
    )
    transform_complete = next(
        event for event in progress_events if event.get("event") == "transform_complete"
    )
    assert transform_start["current_word"] == "hola"
    assert transform_start["words_left"] == 1
    assert transform_complete["current_word"] == "hola"
    assert transform_complete["words_left"] == 0


def test_execute_pipeline_run_parallel_word_branches_emits_running_and_queue_data(
    tmp_path, monkeypatch
):
    service = PipelineRunService()
    db_client = _FakePipelineDBClient()
    all_transforms = {
        "Audio": _DummyAudioTransform(),
        "LLM (Meanings/Sentences)": _DummyLlmMeaningTransform(),
        "LLM Image Prompt (Visual Translator)": _DummyImagePromptTransform(),
        "LLM Audio (Sentences)": _DummyLlmAudioTransform(),
        "LLM Image Renderer (Master Prompt)": _DummyImageRendererTransform(),
    }
    monkeypatch.setattr(result_store, "PIPELINE_RESULTS_ROOT", tmp_path / "results")
    progress_events = []

    prepared = service.prepare_pipeline_run(
        pipeline_db_client=db_client,
        all_transformations=all_transforms,
        ordered_transform_names=[
            "Audio",
            "LLM (Meanings/Sentences)",
            "LLM Image Prompt (Visual Translator)",
            "LLM Audio (Sentences)",
            "LLM Image Renderer (Master Prompt)",
        ],
        llm_profile_id="lotm_zh_en_es",
        llm_source_language="Chinese (Simplified)",
    )

    run_result = service.execute_pipeline_run(
        prepared_run=prepared,
        words=["你好", "谢谢"],
        llm_profile_id="lotm_zh_en_es",
        progress_callback=progress_events.append,
        execution_mode="parallel_word_branches",
    )

    assert set(run_result.df_results["word"]) == {"你好", "谢谢"}
    assert "audio" in run_result.df_results.columns
    assert "sentence_1" in run_result.df_results.columns
    assert "sentence_1_audio" in run_result.df_results.columns
    assert "master_image_prompt" in run_result.df_results.columns
    assert "image" in run_result.df_results.columns

    llm_queue = next(
        event
        for event in progress_events
        if event.get("event") == "transform_queue"
        and event.get("transform_name") == "_DummyLlmMeaningTransform"
    )
    assert llm_queue["queued_words"] == ["你好", "谢谢"]

    llm_starts = [
        event
        for event in progress_events
        if event.get("event") == "transform_start"
        and event.get("transform_name") == "_DummyLlmMeaningTransform"
    ]
    assert len(llm_starts) == 2
    assert llm_starts[0]["current_word"] == "你好"
    assert llm_starts[0]["running_words"] == ["你好"]
    assert llm_starts[0]["queued_words"] == ["谢谢"]
    assert llm_starts[1]["current_word"] == "谢谢"

    llm_audio_starts = [
        event
        for event in progress_events
        if event.get("event") == "transform_start"
        and event.get("transform_name") == "_DummyLlmAudioTransform"
    ]
    assert len(llm_audio_starts) == 2
    assert llm_audio_starts[0]["current_word"] == "你好"
    assert llm_audio_starts[1]["current_word"] == "谢谢"

    llm_audio_queue = next(
        event
        for event in progress_events
        if event.get("event") == "transform_queue"
        and event.get("transform_name") == "_DummyLlmAudioTransform"
    )
    assert llm_audio_queue["queued_words"] == ["你好", "谢谢"]

    llm_meaning_complete_index = next(
        idx
        for idx, event in enumerate(progress_events)
        if event.get("event") == "transform_complete"
        and event.get("transform_name") == "_DummyLlmMeaningTransform"
        and event.get("current_word") == "你好"
    )
    llm_audio_start_index = next(
        idx
        for idx, event in enumerate(progress_events)
        if event.get("event") == "transform_start"
        and event.get("transform_name") == "_DummyLlmAudioTransform"
        and event.get("current_word") == "你好"
    )
    assert llm_audio_start_index > llm_meaning_complete_index

    image_prompt_complete_index = next(
        idx
        for idx, event in enumerate(progress_events)
        if event.get("event") == "transform_complete"
        and event.get("transform_name") == "_DummyImagePromptTransform"
        and event.get("current_word") == "你好"
    )
    image_renderer_start_index = next(
        idx
        for idx, event in enumerate(progress_events)
        if event.get("event") == "transform_start"
        and event.get("transform_name") == "_DummyImageRendererTransform"
        and event.get("current_word") == "你好"
    )
    assert image_renderer_start_index > image_prompt_complete_index

    llm_meaning_second_start = next(
        idx
        for idx, event in enumerate(progress_events)
        if event.get("event") == "transform_start"
        and event.get("transform_name") == "_DummyLlmMeaningTransform"
        and event.get("current_word") == "谢谢"
    )
    image_renderer_first_complete = next(
        idx
        for idx, event in enumerate(progress_events)
        if event.get("event") == "transform_complete"
        and event.get("transform_name") == "_DummyImageRendererTransform"
        and event.get("current_word") == "你好"
    )
    assert llm_meaning_second_start < image_renderer_first_complete


def test_parallel_word_branches_does_not_skip_llm_sentence_audio_for_new_words(
    tmp_path, monkeypatch
):
    class LLMAudioTransformation(Transformation):
        pipeline_stage = "llm"
        required_input_columns = ("sentence_1",)

        def __init__(self):
            self.calls = 0

        @property
        def column_name(self) -> str:
            return "sentence_1_audio"

        def apply(self, df: pd.DataFrame) -> pd.DataFrame:
            self.calls += 1
            output = df.copy()
            output["sentence_1_audio"] = output["sentence_1"].astype(str).map(
                lambda sentence: f"A:{sentence}"
            )
            return output

    service = PipelineRunService()
    db_client = _FakePipelineDBClient()
    llm_audio_transform = LLMAudioTransformation()
    all_transforms = {
        "LLM (Meanings/Sentences)": _DummyLlmMeaningTransform(),
        "LLM Audio (Sentences)": llm_audio_transform,
    }
    monkeypatch.setattr(result_store, "PIPELINE_RESULTS_ROOT", tmp_path / "results")
    progress_events = []

    prepared = service.prepare_pipeline_run(
        pipeline_db_client=db_client,
        all_transformations=all_transforms,
        ordered_transform_names=[
            "LLM (Meanings/Sentences)",
            "LLM Audio (Sentences)",
        ],
        llm_profile_id="lotm_zh_en_es",
        llm_source_language="Chinese (Simplified)",
    )

    run_result = service.execute_pipeline_run(
        prepared_run=prepared,
        words=["你好"],
        llm_profile_id="lotm_zh_en_es",
        progress_callback=progress_events.append,
        execution_mode="parallel_word_branches",
    )

    llm_audio_starts = [
        event
        for event in progress_events
        if event.get("event") == "transform_start"
        and event.get("transform_name") == "LLMAudioTransformation"
    ]
    assert len(llm_audio_starts) == 1
    assert llm_audio_transform.calls == 1
    assert run_result.df_results.loc[0, "sentence_1_audio"] == "A:S:你好"


def test_execute_pipeline_run_parallel_word_branches_skips_cached_partial_word(
    tmp_path, monkeypatch
):
    class _CountingAudioTransform(_DummyAudioTransform):
        def __init__(self):
            self.calls = []

        def apply(self, df: pd.DataFrame) -> pd.DataFrame:
            self.calls.append(df["word"].astype(str).tolist())
            return super().apply(df)

    service = PipelineRunService()
    db_client = _FakePipelineDBClient()
    db_client.rows["你好"] = {"word": "你好", "audio": "cached://你好"}
    audio_transform = _CountingAudioTransform()
    all_transforms = {
        "Audio": audio_transform,
        "LLM (Meanings/Sentences)": _DummyLlmMeaningTransform(),
    }
    monkeypatch.setattr(result_store, "PIPELINE_RESULTS_ROOT", tmp_path / "results")
    progress_events = []

    prepared = service.prepare_pipeline_run(
        pipeline_db_client=db_client,
        all_transformations=all_transforms,
        ordered_transform_names=[
            "Audio",
            "LLM (Meanings/Sentences)",
        ],
        llm_profile_id="lotm_zh_en_es",
        llm_source_language="Chinese (Simplified)",
    )

    run_result = service.execute_pipeline_run(
        prepared_run=prepared,
        words=["你好", "谢谢"],
        llm_profile_id="lotm_zh_en_es",
        progress_callback=progress_events.append,
        execution_mode="parallel_word_branches",
    )

    cache_checked_event = next(
        event for event in progress_events if event.get("event") == "cache_checked"
    )
    assert cache_checked_event["cached_words"] == 1
    assert cache_checked_event["new_words"] == 1
    assert cache_checked_event["backfill_words"] == 1

    audio_queue_event = next(
        event
        for event in progress_events
        if event.get("event") == "transform_queue"
        and event.get("transform_name") == "_CountingAudioTransform"
    )
    assert audio_queue_event["queued_words"] == ["谢谢"]

    audio_starts = [
        event
        for event in progress_events
        if event.get("event") == "transform_start"
        and event.get("transform_name") == "_CountingAudioTransform"
    ]
    assert len(audio_starts) == 1
    assert audio_starts[0]["current_word"] == "谢谢"
    assert audio_transform.calls == [["谢谢"]]

    result_rows = run_result.df_results.set_index("word")
    assert result_rows.loc["你好", "audio"] == "cached://你好"
    assert result_rows.loc["谢谢", "audio"] == "A:谢谢"


def test_add_category_to_results_updates_dataframe_with_joined_categories():
    service = PipelineRunService()
    db_client = _FakePipelineDBClient()
    df = pd.DataFrame({"word": ["你好", "谢谢"]})

    categorized = service.add_category_to_results(
        pipeline_db_client=db_client,
        df_results=df,
        category="HSK1",
    )

    assert "categories" in categorized.columns
    assert categorized["categories"].tolist() == ["HSK1", "HSK1"]


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("  HSK1  ", "HSK1"),
        ("My List", "My List"),
        ("A_B-C 1", "A_B-C 1"),
    ],
)
def test_normalize_category_name_accepts_and_trims_valid_values(raw, expected):
    service = PipelineRunService()

    assert service.normalize_category_name(raw) == expected


@pytest.mark.parametrize(
    "raw,expected_error",
    [
        ("", "Please enter a category name."),
        (" ", "Please enter a category name."),
        ("A", "Category name must be at least 2 characters long."),
        (
            "bad/category",
            "Category name contains invalid characters.",
        ),
    ],
)
def test_normalize_category_name_rejects_invalid_values(raw, expected_error):
    service = PipelineRunService()

    with pytest.raises(ValueError, match=expected_error):
        service.normalize_category_name(raw)


def test_validate_transform_run_selection_requires_configured_transforms():
    service = PipelineRunService()
    profile = _build_test_profile(supports_images=True)

    error = service.validate_transform_run_selection(
        all_transformations={},
        ordered_transform_names=[],
        selected_profile=profile,
    )

    assert error == "No runnable transformations are configured."


def test_validate_transform_run_selection_blocks_images_for_unsupported_profile():
    service = PipelineRunService()
    profile = _build_test_profile(supports_images=False)
    prompt_transform = object.__new__(LLMImagePromptTransformation)

    error = service.validate_transform_run_selection(
        all_transformations={"image_prompt": prompt_transform},
        ordered_transform_names=["image_prompt"],
        selected_profile=profile,
    )

    assert error is not None
    assert "does not support image transforms" in error


def test_validate_transform_run_selection_requires_prompt_before_renderer():
    service = PipelineRunService()
    profile = _build_test_profile(supports_images=True)
    render_transform = object.__new__(LLMImageTransformation)

    error = service.validate_transform_run_selection(
        all_transformations={"image_render": render_transform},
        ordered_transform_names=["image_render"],
        selected_profile=profile,
    )

    assert error == (
        "LLM Image Renderer requires LLM Image Prompt (Visual Translator). "
        "Select both stages."
    )


def test_validate_transform_run_selection_accepts_valid_image_stages():
    service = PipelineRunService()
    profile = _build_test_profile(supports_images=True)
    prompt_transform = object.__new__(LLMImagePromptTransformation)
    render_transform = object.__new__(LLMImageTransformation)

    error = service.validate_transform_run_selection(
        all_transformations={
            "image_prompt": prompt_transform,
            "image_render": render_transform,
        },
        ordered_transform_names=["image_prompt", "image_render"],
        selected_profile=profile,
    )

    assert error is None


def test_prepare_pipeline_run_uses_context_aware_transform_factory_without_mutating_preview_map():
    service = PipelineRunService()
    db_client = _FakePipelineDBClient()
    preview_transform = _SourceAwareDummyTransform(source_language="Preview")
    all_transforms = {"source_debug": preview_transform}

    def _context_factory(llm_profile_id, llm_source_language):
        del llm_profile_id
        return {"source_debug": _SourceAwareDummyTransform(llm_source_language)}

    prepared = service.prepare_pipeline_run(
        pipeline_db_client=db_client,
        all_transformations=all_transforms,
        ordered_transform_names=["source_debug"],
        llm_profile_id="sp_russian",
        llm_source_language="Russian",
        transform_factory=_context_factory,
    )

    selected_transform = prepared.selected_transforms[0]
    assert isinstance(selected_transform, _SourceAwareDummyTransform)
    assert selected_transform.source_language == "Russian"
    assert all_transforms["source_debug"].source_language == "Preview"
