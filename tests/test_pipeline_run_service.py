"""Unit tests for application-level pipeline orchestration service."""

from typing import Any, Dict

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
    )

    assert set(run_result.df_results["word"]) == {"hola", "adios"}
    assert "translation" in run_result.df_results.columns
    assert run_result.saved_results_csv.exists()
    assert run_result.saved_results_csv.parent == tmp_path / "results" / "lotm_zh_en_es"


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
