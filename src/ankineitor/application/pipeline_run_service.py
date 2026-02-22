"""Service layer for pipeline runs outside Streamlit/UI concerns."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from ..common.pipeline_result_store import save_pipeline_results_csv
from ..pipeline import TransformationPipeline
from ..pipeline.llm_audio_transformation import LLMAudioTransformation
from ..pipeline.llm_image_prompt_transformation import LLMImagePromptTransformation
from ..pipeline.llm_image_transformation import LLMImageTransformation
from ..pipeline.llm_profiles import LLMProfile, get_llm_profile
from ..pipeline.llm_transformation import LLMTransformation
from ..pipeline.transformations import (
    AudioTransformation,
    PinyinTransformation,
    TimestampTransformation,
    Transformation,
    TranslationTransformation,
)


@dataclass
class TransformOptions:
    available_transform_names: List[str]
    unavailable_transform_reasons: Dict[str, str]
    always_included_transform_names: List[str]


@dataclass
class PreparedPipelineRun:
    ordered_transform_names: List[str]
    selected_transforms: List[Transformation]
    pipeline: TransformationPipeline


@dataclass
class PipelineRunResult:
    df_results: pd.DataFrame
    saved_results_csv: Path


class PipelineRunService:
    """Coordinates transform selection, pipeline execution, and result persistence."""

    @staticmethod
    def _get_unavailable_transform_reason(
        transform_name: str,
        transform: object,
        selected_profile: LLMProfile,
    ) -> Optional[str]:
        del transform_name
        if isinstance(transform, LLMTransformation):
            return "Always included automatically (core profile prompt stage)."
        if isinstance(transform, TimestampTransformation):
            return "Always included automatically (creation timestamp)."
        if isinstance(transform, PinyinTransformation):
            return "Provided by the profile prompt output."
        if isinstance(transform, TranslationTransformation):
            return "Provided by the profile prompt output."
        if isinstance(transform, AudioTransformation):
            if selected_profile.always_include_audio_transforms:
                return "Always included automatically for this profile."
            return "Use the single profile-aware sentence audio transform."
        if (
            isinstance(transform, LLMAudioTransformation)
            and selected_profile.always_include_audio_transforms
        ):
            return "Always included automatically for this profile."
        if isinstance(transform, (LLMImagePromptTransformation, LLMImageTransformation)):
            if not selected_profile.supports_images:
                return "Image transforms are disabled for this profile."
        return None

    def resolve_transform_options_for_profile(
        self,
        all_transformations: Dict[str, object],
        selected_profile: LLMProfile,
    ) -> TransformOptions:
        available_names: List[str] = []
        unavailable_reasons: Dict[str, str] = {}
        always_included_names: List[str] = []

        for name, transform in all_transformations.items():
            if isinstance(transform, (LLMTransformation, TimestampTransformation)):
                always_included_names.append(name)
            if selected_profile.always_include_audio_transforms and isinstance(
                transform, (AudioTransformation, LLMAudioTransformation)
            ):
                always_included_names.append(name)
            reason = self._get_unavailable_transform_reason(
                transform_name=name,
                transform=transform,
                selected_profile=selected_profile,
            )
            if reason:
                unavailable_reasons[name] = reason
            else:
                available_names.append(name)

        return TransformOptions(
            available_transform_names=available_names,
            unavailable_transform_reasons=unavailable_reasons,
            always_included_transform_names=always_included_names,
        )

    @staticmethod
    def default_transform_selection(
        available_transform_names: List[str],
        selected_profile: LLMProfile,
    ) -> List[str]:
        preferred = list(selected_profile.default_optional_transform_names)
        return [name for name in preferred if name in available_transform_names]

    @staticmethod
    def build_ordered_transform_names(
        all_transformations: Dict[str, object],
        always_included_transform_names: List[str],
        selected_transform_names: List[str],
    ) -> List[str]:
        ordered_transform_names: List[str] = []
        for name in always_included_transform_names + selected_transform_names:
            if name in all_transformations and name not in ordered_transform_names:
                ordered_transform_names.append(name)
        return ordered_transform_names

    @staticmethod
    def validate_transform_run_selection(
        *,
        all_transformations: Dict[str, object],
        ordered_transform_names: List[str],
        selected_profile: LLMProfile,
    ) -> Optional[str]:
        selected_transforms = [
            all_transformations[name]
            for name in ordered_transform_names
            if name in all_transformations
        ]
        if not selected_transforms:
            return "No runnable transformations are configured."

        has_image_prompt = any(
            isinstance(transform, LLMImagePromptTransformation)
            for transform in selected_transforms
        )
        has_image_renderer = any(
            isinstance(transform, LLMImageTransformation)
            for transform in selected_transforms
        )

        if (has_image_prompt or has_image_renderer) and not selected_profile.supports_images:
            return (
                f"Profile '{selected_profile.display_name}' does not support image transforms. "
                "Deselect image prompt/renderer for this profile."
            )
        if has_image_renderer and not has_image_prompt:
            return (
                "LLM Image Renderer requires LLM Image Prompt (Visual Translator). "
                "Select both stages."
            )
        return None

    def prepare_pipeline_run(
        self,
        *,
        pipeline_db_client: Any,
        all_transformations: Dict[str, object],
        ordered_transform_names: List[str],
        llm_profile_id: str,
        llm_source_language: str,
        transform_factory: Optional[Callable[..., Dict[str, object]]] = None,
        table_name: str = "hanzi_processing",
    ) -> PreparedPipelineRun:
        runtime_transformations, requires_legacy_mutation = self._build_runtime_transformations(
            all_transformations=all_transformations,
            transform_factory=transform_factory,
            llm_profile_id=llm_profile_id,
            llm_source_language=llm_source_language,
        )

        missing_runtime_transforms = [
            name for name in ordered_transform_names if name not in runtime_transformations
        ]
        if missing_runtime_transforms:
            raise ValueError(
                "Runtime transform builder is missing configured transform(s): "
                + ", ".join(missing_runtime_transforms)
            )

        selected_transforms = [runtime_transformations[name] for name in ordered_transform_names]
        if requires_legacy_mutation:
            self._apply_legacy_runtime_configuration(
                selected_transforms=selected_transforms,
                llm_profile_id=llm_profile_id,
                llm_source_language=llm_source_language,
            )

        pipeline = TransformationPipeline(
            db_client=pipeline_db_client,
            transformations=selected_transforms,
            table_name=table_name,
        )
        return PreparedPipelineRun(
            ordered_transform_names=list(ordered_transform_names),
            selected_transforms=selected_transforms,
            pipeline=pipeline,
        )

    def execute_pipeline_run(
        self,
        *,
        prepared_run: PreparedPipelineRun,
        words: List[str],
        llm_profile_id: str,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        dev_mode: bool = False,
    ) -> PipelineRunResult:
        df_results = prepared_run.pipeline.transform_data_with_progress(
            words=words,
            dev_mode=dev_mode,
            progress_callback=progress_callback,
        )
        saved_results_csv = save_pipeline_results_csv(
            df_results=df_results,
            profile_id=llm_profile_id,
        )
        return PipelineRunResult(
            df_results=df_results,
            saved_results_csv=saved_results_csv,
        )

    def add_category_to_results(
        self,
        *,
        pipeline_db_client: Any,
        df_results: pd.DataFrame,
        category: str,
        table_name: str = "hanzi_processing",
    ) -> pd.DataFrame:
        pipeline = TransformationPipeline(
            db_client=pipeline_db_client,
            transformations=[],
            table_name=table_name,
        )
        return pipeline.transform_categories(df_results, category=category)

    @staticmethod
    def _build_runtime_transformations(
        *,
        all_transformations: Dict[str, object],
        transform_factory: Optional[Callable[..., Dict[str, object]]],
        llm_profile_id: str,
        llm_source_language: str,
    ) -> tuple[Dict[str, object], bool]:
        if not callable(transform_factory):
            return all_transformations, True

        try:
            signature = inspect.signature(transform_factory)
        except (TypeError, ValueError):
            return transform_factory(), True
        accepted_params = set(signature.parameters.keys())
        accepts_var_kwargs = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        )
        runtime_kwargs = {}
        if accepts_var_kwargs or "llm_profile_id" in accepted_params:
            runtime_kwargs["llm_profile_id"] = llm_profile_id
        if accepts_var_kwargs or "llm_source_language" in accepted_params:
            runtime_kwargs["llm_source_language"] = llm_source_language

        if runtime_kwargs:
            runtime_transformations = transform_factory(**runtime_kwargs)
            return runtime_transformations, False

        return transform_factory(), True

    @staticmethod
    def _apply_legacy_runtime_configuration(
        *,
        selected_transforms: List[object],
        llm_profile_id: str,
        llm_source_language: str,
    ) -> None:
        for transform in selected_transforms:
            if hasattr(transform, "source_language"):
                transform.source_language = llm_source_language
            if isinstance(transform, LLMTransformation):
                transform.profile_id = llm_profile_id
                transform.profile = get_llm_profile(llm_profile_id)
            if isinstance(transform, LLMAudioTransformation):
                transform.profile_id = llm_profile_id
