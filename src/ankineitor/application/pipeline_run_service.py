"""Service layer for pipeline runs outside Streamlit/UI concerns."""

from __future__ import annotations

import inspect
import re
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


class TransformSelectionService:
    """Owns transform filtering, defaults, and selection validation rules."""

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
        return TransformSelectionService._reorder_with_dependencies(
            ordered_transform_names=ordered_transform_names,
            all_transformations=all_transformations,
        )

    @staticmethod
    def _required_input_columns(transform: object) -> tuple[str, ...]:
        required_columns = getattr(transform, "required_input_columns", ())
        if isinstance(required_columns, str):
            return (required_columns,)
        if isinstance(required_columns, tuple):
            return tuple(str(column) for column in required_columns if str(column))
        if isinstance(required_columns, list):
            return tuple(str(column) for column in required_columns if str(column))
        return ()

    @staticmethod
    def _resolve_transform_dependencies(
        *,
        ordered_transform_names: List[str],
        all_transformations: Dict[str, object],
    ) -> Dict[str, set[str]]:
        dependencies: Dict[str, set[str]] = {
            name: set() for name in ordered_transform_names
        }
        column_producers: Dict[str, List[str]] = {}

        for name in ordered_transform_names:
            transform = all_transformations.get(name)
            produced_column = str(getattr(transform, "column_name", "") or "").strip()
            if produced_column:
                column_producers.setdefault(produced_column, []).append(name)

        for name in ordered_transform_names:
            transform = all_transformations.get(name)
            if transform is None:
                continue

            for required_column in TransformSelectionService._required_input_columns(
                transform
            ):
                for producer_name in column_producers.get(required_column, []):
                    if producer_name != name:
                        dependencies[name].add(producer_name)

            if isinstance(transform, LLMAudioTransformation):
                llm_stage = next(
                    (
                        candidate_name
                        for candidate_name in ordered_transform_names
                        if candidate_name != name
                        and isinstance(
                            all_transformations.get(candidate_name), LLMTransformation
                        )
                    ),
                    None,
                )
                if llm_stage:
                    dependencies[name].add(llm_stage)

            if isinstance(transform, LLMImageTransformation):
                image_prompt_stage = next(
                    (
                        candidate_name
                        for candidate_name in ordered_transform_names
                        if candidate_name != name
                        and isinstance(
                            all_transformations.get(candidate_name),
                            LLMImagePromptTransformation,
                        )
                    ),
                    None,
                )
                if image_prompt_stage:
                    dependencies[name].add(image_prompt_stage)

        return dependencies

    @staticmethod
    def _reorder_with_dependencies(
        *,
        ordered_transform_names: List[str],
        all_transformations: Dict[str, object],
    ) -> List[str]:
        dependencies = TransformSelectionService._resolve_transform_dependencies(
            ordered_transform_names=ordered_transform_names,
            all_transformations=all_transformations,
        )
        pending = set(ordered_transform_names)
        reordered: List[str] = []

        while pending:
            progressed = False
            for name in ordered_transform_names:
                if name not in pending:
                    continue
                blocked_by = dependencies.get(name, set()) & pending
                if blocked_by:
                    continue
                reordered.append(name)
                pending.remove(name)
                progressed = True

            if progressed:
                continue

            # Fallback for malformed dependency graphs: preserve remaining original order.
            reordered.extend([name for name in ordered_transform_names if name in pending])
            break

        return reordered

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


class PipelinePreparationService:
    """Builds a concrete runtime pipeline from selected transform names."""

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
            if isinstance(transform, LLMImageTransformation):
                transform.profile_id = llm_profile_id


class PipelineExecutionService:
    """Executes a prepared pipeline and persists run artifacts."""

    def execute_pipeline_run(
        self,
        *,
        prepared_run: PreparedPipelineRun,
        words: List[str],
        llm_profile_id: str,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        dev_mode: bool = False,
        execution_mode: str = "default",
    ) -> PipelineRunResult:
        df_results = prepared_run.pipeline.transform_data_with_progress(
            words=words,
            dev_mode=dev_mode,
            progress_callback=progress_callback,
            execution_mode=execution_mode,
        )
        saved_results_csv = save_pipeline_results_csv(
            df_results=df_results,
            profile_id=llm_profile_id,
        )
        return PipelineRunResult(
            df_results=df_results,
            saved_results_csv=saved_results_csv,
        )


class CategoryService:
    """Validates and applies category updates for pipeline results."""

    _CATEGORY_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\s]+$")

    @classmethod
    def normalize_category_name(cls, category: str) -> str:
        normalized = str(category or "").strip()
        if not normalized:
            raise ValueError("Please enter a category name.")
        if len(normalized) < 2:
            raise ValueError("Category name must be at least 2 characters long.")
        if not cls._CATEGORY_NAME_PATTERN.fullmatch(normalized):
            raise ValueError(
                "Category name contains invalid characters. "
                "Use only letters, numbers, spaces, hyphens, and underscores."
            )
        return normalized

    def add_category_to_results(
        self,
        *,
        pipeline_db_client: Any,
        df_results: pd.DataFrame,
        category: str,
        table_name: str = "hanzi_processing",
    ) -> pd.DataFrame:
        normalized_category = self.normalize_category_name(category)
        pipeline = TransformationPipeline(
            db_client=pipeline_db_client,
            transformations=[],
            table_name=table_name,
        )
        return pipeline.transform_categories(df_results, category=normalized_category)


class PipelineRunService:
    """Facade that coordinates pipeline selection, build, execution, and categories."""

    def __init__(
        self,
        *,
        transform_selection_service: Optional[TransformSelectionService] = None,
        pipeline_preparation_service: Optional[PipelinePreparationService] = None,
        pipeline_execution_service: Optional[PipelineExecutionService] = None,
        category_service: Optional[CategoryService] = None,
    ):
        self.transform_selection_service = (
            transform_selection_service or TransformSelectionService()
        )
        self.pipeline_preparation_service = (
            pipeline_preparation_service or PipelinePreparationService()
        )
        self.pipeline_execution_service = (
            pipeline_execution_service or PipelineExecutionService()
        )
        self.category_service = category_service or CategoryService()

    def resolve_transform_options_for_profile(
        self,
        all_transformations: Dict[str, object],
        selected_profile: LLMProfile,
    ) -> TransformOptions:
        return self.transform_selection_service.resolve_transform_options_for_profile(
            all_transformations=all_transformations,
            selected_profile=selected_profile,
        )

    def default_transform_selection(
        self,
        available_transform_names: List[str],
        selected_profile: LLMProfile,
    ) -> List[str]:
        return self.transform_selection_service.default_transform_selection(
            available_transform_names=available_transform_names,
            selected_profile=selected_profile,
        )

    def build_ordered_transform_names(
        self,
        all_transformations: Dict[str, object],
        always_included_transform_names: List[str],
        selected_transform_names: List[str],
    ) -> List[str]:
        return self.transform_selection_service.build_ordered_transform_names(
            all_transformations=all_transformations,
            always_included_transform_names=always_included_transform_names,
            selected_transform_names=selected_transform_names,
        )

    def validate_transform_run_selection(
        self,
        *,
        all_transformations: Dict[str, object],
        ordered_transform_names: List[str],
        selected_profile: LLMProfile,
    ) -> Optional[str]:
        return self.transform_selection_service.validate_transform_run_selection(
            all_transformations=all_transformations,
            ordered_transform_names=ordered_transform_names,
            selected_profile=selected_profile,
        )

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
        return self.pipeline_preparation_service.prepare_pipeline_run(
            pipeline_db_client=pipeline_db_client,
            all_transformations=all_transformations,
            ordered_transform_names=ordered_transform_names,
            llm_profile_id=llm_profile_id,
            llm_source_language=llm_source_language,
            transform_factory=transform_factory,
            table_name=table_name,
        )

    def execute_pipeline_run(
        self,
        *,
        prepared_run: PreparedPipelineRun,
        words: List[str],
        llm_profile_id: str,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        dev_mode: bool = False,
        execution_mode: str = "default",
    ) -> PipelineRunResult:
        return self.pipeline_execution_service.execute_pipeline_run(
            prepared_run=prepared_run,
            words=words,
            llm_profile_id=llm_profile_id,
            progress_callback=progress_callback,
            dev_mode=dev_mode,
            execution_mode=execution_mode,
        )

    @classmethod
    def normalize_category_name(cls, category: str) -> str:
        del cls
        return CategoryService.normalize_category_name(category)

    def add_category_to_results(
        self,
        *,
        pipeline_db_client: Any,
        df_results: pd.DataFrame,
        category: str,
        table_name: str = "hanzi_processing",
    ) -> pd.DataFrame:
        return self.category_service.add_category_to_results(
            pipeline_db_client=pipeline_db_client,
            df_results=df_results,
            category=category,
            table_name=table_name,
        )

    @staticmethod
    def _build_runtime_transformations(
        *,
        all_transformations: Dict[str, object],
        transform_factory: Optional[Callable[..., Dict[str, object]]],
        llm_profile_id: str,
        llm_source_language: str,
    ) -> tuple[Dict[str, object], bool]:
        return PipelinePreparationService._build_runtime_transformations(
            all_transformations=all_transformations,
            transform_factory=transform_factory,
            llm_profile_id=llm_profile_id,
            llm_source_language=llm_source_language,
        )

    @staticmethod
    def _apply_legacy_runtime_configuration(
        *,
        selected_transforms: List[object],
        llm_profile_id: str,
        llm_source_language: str,
    ) -> None:
        PipelinePreparationService._apply_legacy_runtime_configuration(
            selected_transforms=selected_transforms,
            llm_profile_id=llm_profile_id,
            llm_source_language=llm_source_language,
        )
