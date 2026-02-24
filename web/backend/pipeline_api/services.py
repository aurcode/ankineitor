from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.utils import timezone
from loguru import logger

from ankineitor.application import PipelineProgressTracker, PipelineRunService
from ankineitor.config import get_settings
from ankineitor.pipeline.audio_creator import AudioCreator
from ankineitor.pipeline.db_client import SQLAlchemyClient
from ankineitor.pipeline.llm_audio_transformation import LLMAudioTransformation
from ankineitor.pipeline.llm_image_prompt_transformation import LLMImagePromptTransformation
from ankineitor.pipeline.llm_image_transformation import LLMImageTransformation
from ankineitor.pipeline.llm_profiles import (
    DEFAULT_LLM_PROFILE_ID,
    get_llm_profile,
    list_llm_profiles,
)
from ankineitor.pipeline.llm_transformation import LLMTransformation
from ankineitor.pipeline.transformations import (
    AudioTransformation,
)

from .models import PipelineResultRow, PipelineRun, PipelineRunEvent, RunStatus


RUN_GROUP_PREFIX = "pipeline_run_"
PIPELINE_TERMINAL_STATUSES = {RunStatus.SUCCESS, RunStatus.ERROR, RunStatus.CANCELED}
HIDDEN_RESULT_COLUMNS = {"pinyin", "translation"}


class RunPausedError(RuntimeError):
    pass


class RunCanceledError(RuntimeError):
    pass


@dataclass
class PipelineRuntime:
    pipeline_db_client: SQLAlchemyClient
    all_transformations: Dict[str, object]
    transform_factory: Any


_runtime_lock = threading.Lock()
_runtime_instance: Optional[PipelineRuntime] = None


def _to_json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (list, tuple, set)):
        return [_to_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _to_json_safe(item) for key, item in value.items()}
    if isinstance(value, float) and pd.isna(value):
        return None
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
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    return value


def _dataframe_row_to_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        str(key): _to_json_safe(value)
        for key, value in row.items()
        if str(key) not in HIDDEN_RESULT_COLUMNS
    }


def _sanitize_pipeline_results_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    removable_columns = [
        column
        for column in HIDDEN_RESULT_COLUMNS
        if column in df.columns
    ]
    if not removable_columns:
        return df
    return df.drop(columns=removable_columns)


def _build_runtime_transformations(
    *,
    llm_profile_id: str = DEFAULT_LLM_PROFILE_ID,
    llm_source_language: str = "",
    llm_db_client: SQLAlchemyClient,
    audio_creator: AudioCreator,
) -> Dict[str, object]:
    profile_id = (llm_profile_id or DEFAULT_LLM_PROFILE_ID).strip()
    source_language = (
        llm_source_language
        or get_llm_profile(profile_id).source_language
        or "Chinese (Simplified)"
    )

    return {
        "Audio": AudioTransformation(
            audio_creator=audio_creator,
            source_language=source_language,
        ),
        "LLM (Meanings/Sentences)": LLMTransformation(
            db_client=llm_db_client,
            profile_id=profile_id,
        ),
        "LLM Image Prompt (Visual Translator)": LLMImagePromptTransformation(
            db_client=llm_db_client,
            source_language=source_language,
        ),
        "LLM Image Renderer (Master Prompt)": LLMImageTransformation(
            profile_id=profile_id,
        ),
        "LLM Audio (Sentences)": LLMAudioTransformation(
            audio_creator=audio_creator,
            source_language=source_language,
            profile_id=profile_id,
        ),
    }


def get_pipeline_runtime() -> PipelineRuntime:
    global _runtime_instance
    with _runtime_lock:
        if _runtime_instance is not None:
            return _runtime_instance

        settings = get_settings()
        pipeline_db = SQLAlchemyClient(db_path=settings.pipeline_db_path)
        llm_db = SQLAlchemyClient(db_path=settings.llm_cache_db_path)
        audio_creator = AudioCreator(folder_name=settings.audio_output_dir)

        def _transform_factory(
            llm_profile_id: str = DEFAULT_LLM_PROFILE_ID,
            llm_source_language: str = "",
        ) -> Dict[str, object]:
            return _build_runtime_transformations(
                llm_profile_id=llm_profile_id,
                llm_source_language=llm_source_language,
                llm_db_client=llm_db,
                audio_creator=audio_creator,
            )

        preview_transformations = _transform_factory()
        _runtime_instance = PipelineRuntime(
            pipeline_db_client=pipeline_db,
            all_transformations=preview_transformations,
            transform_factory=_transform_factory,
        )
        return _runtime_instance


def run_group_name(run_id: str) -> str:
    return f"{RUN_GROUP_PREFIX}{run_id}"


def serialize_event(event: PipelineRunEvent) -> Dict[str, Any]:
    payload = dict(event.payload or {})
    payload.setdefault("event", event.event_type)
    payload.setdefault("stage", event.stage)
    payload.setdefault("transform_name", event.transform_name)
    return {
        "id": event.id,
        "run_id": str(event.run_id),
        "sequence": event.sequence,
        "created_at": event.created_at.isoformat(),
        "payload": payload,
    }


def serialize_run(run: PipelineRun) -> Dict[str, Any]:
    return {
        "id": str(run.id),
        "status": run.status,
        "profile_id": run.profile_id,
        "source_language": run.source_language,
        "selected_transform_names": list(run.selected_transform_names or []),
        "ordered_transform_names": list(run.ordered_transform_names or []),
        "total_input_words": int(run.total_input_words or 0),
        "error_message": run.error_message,
        "csv_output_path": run.csv_output_path,
        "csv_download_name": run.csv_download_name,
        "total_duration_seconds": run.total_duration_seconds,
        "counters": dict(run.counters or {}),
        "slowest_steps": list(run.slowest_steps or []),
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "event_count": run.events.count(),
    }


def record_run_event(run_id: str, payload: Dict[str, Any]) -> PipelineRunEvent:
    normalized_payload = dict(payload or {})
    event_type = str(normalized_payload.get("event", "unknown"))
    stage = str(normalized_payload.get("stage", "") or "")
    transform_name = str(normalized_payload.get("transform_name", "") or "")

    with transaction.atomic():
        run = PipelineRun.objects.select_for_update().get(pk=run_id)
        sequence = int(run.last_event_sequence or 0) + 1
        run.last_event_sequence = sequence
        run.save(update_fields=["last_event_sequence", "updated_at"])
        event = PipelineRunEvent.objects.create(
            run=run,
            sequence=sequence,
            event_type=event_type,
            stage=stage,
            transform_name=transform_name,
            payload=normalized_payload,
        )

    channel_layer = get_channel_layer()
    if channel_layer is not None:
        outbound = serialize_event(event)
        try:
            async_to_sync(channel_layer.group_send)(
                run_group_name(str(run_id)),
                {
                    "type": "pipeline.event",
                    "payload": outbound,
                },
            )
        except Exception as exc:
            logger.warning("Failed to send websocket event for run {}: {}", run_id, exc)

    return event


def build_pipeline_options() -> Dict[str, Any]:
    runtime = get_pipeline_runtime()
    service = PipelineRunService()

    profiles_payload: List[Dict[str, Any]] = []
    for profile in list_llm_profiles():
        options = service.resolve_transform_options_for_profile(
            all_transformations=runtime.all_transformations,
            selected_profile=profile,
        )
        default_selection = service.default_transform_selection(
            available_transform_names=options.available_transform_names,
            selected_profile=profile,
        )
        ordered_default = service.build_ordered_transform_names(
            all_transformations=runtime.all_transformations,
            always_included_transform_names=options.always_included_transform_names,
            selected_transform_names=default_selection,
        )

        profiles_payload.append(
            {
                "profile_id": profile.profile_id,
                "display_name": profile.display_name,
                "description": profile.description,
                "source_language": profile.source_language,
                "supports_images": profile.supports_images,
                "available_transform_names": options.available_transform_names,
                "unavailable_transform_reasons": options.unavailable_transform_reasons,
                "always_included_transform_names": options.always_included_transform_names,
                "default_optional_transform_names": default_selection,
                "default_ordered_transform_names": ordered_default,
            }
        )

    return {
        "profiles": profiles_payload,
        "default_profile_id": DEFAULT_LLM_PROFILE_ID,
    }


def resolve_ordered_transform_names(
    *,
    profile_id: str,
    selected_transform_names: List[str],
) -> tuple[List[str], List[str], str]:
    runtime = get_pipeline_runtime()
    service = PipelineRunService()

    profile = get_llm_profile(profile_id)
    options = service.resolve_transform_options_for_profile(
        all_transformations=runtime.all_transformations,
        selected_profile=profile,
    )

    selected = list(selected_transform_names or [])
    selected = [name for name in selected if name in options.available_transform_names]
    if not selected:
        selected = service.default_transform_selection(
            available_transform_names=options.available_transform_names,
            selected_profile=profile,
        )

    ordered_transform_names = service.build_ordered_transform_names(
        all_transformations=runtime.all_transformations,
        always_included_transform_names=options.always_included_transform_names,
        selected_transform_names=selected,
    )

    selection_error = service.validate_transform_run_selection(
        all_transformations=runtime.all_transformations,
        ordered_transform_names=ordered_transform_names,
        selected_profile=profile,
    )
    if selection_error:
        raise ValueError(selection_error)

    return selected, ordered_transform_names, profile.source_language


def _persist_result_rows(run: PipelineRun, df_results: pd.DataFrame) -> None:
    PipelineResultRow.objects.filter(run=run).delete()
    rows_to_create: List[PipelineResultRow] = []
    for idx, row in enumerate(df_results.to_dict(orient="records")):
        row_data = _dataframe_row_to_dict(row)
        rows_to_create.append(
            PipelineResultRow(
                run=run,
                row_index=idx,
                word=str(row_data.get("word", "")),
                row_data=row_data,
            )
        )
    if rows_to_create:
        PipelineResultRow.objects.bulk_create(rows_to_create, batch_size=200)
    _populate_db_default_timestamps(run)


def _populate_db_default_timestamps(run: PipelineRun) -> None:
    rows_to_update: List[PipelineResultRow] = []
    for row in PipelineResultRow.objects.filter(run=run).order_by("row_index"):
        row_data = dict(row.row_data or {})
        existing_timestamp = str(row_data.get("timestamp", "") or "").strip()
        if existing_timestamp:
            continue
        if row.created_at:
            row_data["timestamp"] = row.created_at.isoformat()
        else:
            row_data["timestamp"] = timezone.now().isoformat()
        row.row_data = row_data
        rows_to_update.append(row)

    if rows_to_update:
        PipelineResultRow.objects.bulk_update(rows_to_update, ["row_data"])


def _rewrite_results_csv_from_db(run: PipelineRun, csv_path: Path) -> None:
    rows = PipelineResultRow.objects.filter(run=run).order_by("row_index")
    records = [dict(row.row_data or {}) for row in rows]
    if not records:
        return
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(records).to_csv(csv_path, index=False)


def execute_pipeline_run(run_id: str) -> None:
    runtime = get_pipeline_runtime()
    service = PipelineRunService()

    run = PipelineRun.objects.get(pk=run_id)
    if run.status in {RunStatus.PAUSED, RunStatus.CANCELED}:
        logger.info("Skipping run {} startup because status is {}", run_id, run.status)
        return
    run.status = RunStatus.RUNNING
    run.started_at = timezone.now()
    run.completed_at = None
    run.error_message = ""
    run.slowest_steps = []
    run.counters = {}
    run.last_event_sequence = 0
    run.total_duration_seconds = None
    run.save(
        update_fields=[
            "status",
            "started_at",
            "completed_at",
            "error_message",
            "slowest_steps",
            "counters",
            "last_event_sequence",
            "total_duration_seconds",
            "updated_at",
        ]
    )
    PipelineRunEvent.objects.filter(run=run).delete()
    PipelineResultRow.objects.filter(run=run).delete()

    selected_profile = get_llm_profile(run.profile_id)
    prepared_run = service.prepare_pipeline_run(
        pipeline_db_client=runtime.pipeline_db_client,
        all_transformations=runtime.all_transformations,
        ordered_transform_names=list(run.ordered_transform_names),
        llm_profile_id=run.profile_id,
        llm_source_language=selected_profile.source_language,
        transform_factory=runtime.transform_factory,
        table_name="hanzi_processing",
    )

    total_transform_steps = max(1, len(prepared_run.ordered_transform_names))
    transform_name_map: Dict[str, str] = {}
    for configured_name, transform in zip(
        prepared_run.ordered_transform_names,
        prepared_run.selected_transforms,
    ):
        transform_name_map[type(transform).__name__] = configured_name

    progress_tracker = PipelineProgressTracker(total_transform_steps=total_transform_steps)
    counters: Dict[str, Any] = {}
    total_duration_seconds = 0.0
    first_input_word = next(
        (
            str(word).strip()
            for word in list(run.input_words or [])
            if str(word or "").strip()
        ),
        "",
    )

    def on_pipeline_progress(event: Dict[str, Any]) -> None:
        nonlocal total_duration_seconds

        def _to_optional_int(value: Any) -> Optional[int]:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        current_status = (
            PipelineRun.objects.filter(pk=run_id).values_list("status", flat=True).first()
        )
        if current_status == RunStatus.PAUSED:
            raise RunPausedError("Paused by admin.")
        if current_status == RunStatus.CANCELED:
            raise RunCanceledError("Canceled by admin.")

        event_type = str(event.get("event", ""))
        if event_type == "cache_checked":
            counters.update(
                {
                    "cached_words": int(event.get("cached_words", 0) or 0),
                    "new_words": int(event.get("new_words", 0) or 0),
                    "backfill_words": int(event.get("backfill_words", 0) or 0),
                    "total_unique_words": int(event.get("total_unique_words", 0) or 0),
                }
            )
        if event_type == "pipeline_complete":
            total_duration_seconds = float(event.get("total_duration_seconds", 0.0) or 0.0)

        snapshot = progress_tracker.consume_event(event)
        transform_name = str(event.get("transform_name", "") or "")
        transform_key = transform_name_map.get(transform_name)
        enriched_event = {
            **event,
            "progress_ratio": snapshot.progress_ratio,
            "status_text": snapshot.status_text,
        }
        if event_type == "transform_queue":
            current_word = str(enriched_event.get("current_word", "") or "").strip()
            if not current_word and first_input_word:
                enriched_event["current_word"] = first_input_word
                current_word = first_input_word

            words_left = _to_optional_int(enriched_event.get("words_left"))
            if words_left is None:
                input_rows = _to_optional_int(event.get("input_rows"))
                if input_rows is None:
                    input_rows = _to_optional_int(run.total_input_words) or 0
                enriched_event["words_left"] = max(input_rows, 0)

        if event_type == "transform_start":
            current_word = str(enriched_event.get("current_word", "") or "").strip()
            if not current_word and first_input_word:
                enriched_event["current_word"] = first_input_word
                current_word = first_input_word

            words_left = _to_optional_int(enriched_event.get("words_left"))
            if words_left is None:
                input_rows = _to_optional_int(event.get("input_rows"))
                if input_rows is None:
                    input_rows = _to_optional_int(run.total_input_words) or 0
                consumed = 1 if current_word else 0
                enriched_event["words_left"] = max(input_rows - consumed, 0)

        if event_type == "transform_complete":
            words_left = _to_optional_int(enriched_event.get("words_left"))
            if words_left is None:
                enriched_event["words_left"] = 0
        if transform_key:
            enriched_event["transform_key"] = transform_key
        record_run_event(str(run.id), enriched_event)

    run_result = service.execute_pipeline_run(
        prepared_run=prepared_run,
        words=list(run.input_words),
        llm_profile_id=run.profile_id,
        progress_callback=on_pipeline_progress,
        dev_mode=False,
        execution_mode="parallel_word_branches",
    )

    sanitized_df_results = _sanitize_pipeline_results_df(run_result.df_results)
    run_result.df_results = sanitized_df_results
    _persist_result_rows(run, sanitized_df_results)

    saved_results_path = Path(run_result.saved_results_csv)
    _rewrite_results_csv_from_db(run, saved_results_path)
    try:
        csv_relative_path = str(saved_results_path.resolve().relative_to(Path.cwd().resolve()))
    except Exception:
        csv_relative_path = saved_results_path.as_posix()

    run.status = RunStatus.SUCCESS
    run.completed_at = timezone.now()
    run.csv_output_path = csv_relative_path
    run.csv_download_name = saved_results_path.name
    run.counters = counters
    run.slowest_steps = progress_tracker.slowest_steps(limit=3)
    run.total_duration_seconds = total_duration_seconds
    run.save(
        update_fields=[
            "status",
            "completed_at",
            "csv_output_path",
            "csv_download_name",
            "counters",
            "slowest_steps",
            "total_duration_seconds",
            "updated_at",
        ]
    )


def mark_run_error(run_id: str, error_message: str) -> None:
    run = PipelineRun.objects.get(pk=run_id)
    if run.status in {RunStatus.PAUSED, RunStatus.CANCELED}:
        return
    run.status = RunStatus.ERROR
    run.completed_at = timezone.now()
    run.error_message = str(error_message)
    run.save(update_fields=["status", "completed_at", "error_message", "updated_at"])

    record_run_event(
        run_id,
        {
            "event": "pipeline_error",
            "error": str(error_message),
            "status_text": str(error_message),
        },
    )


def mark_run_retrying(run_id: str, error_message: str) -> None:
    run = PipelineRun.objects.get(pk=run_id)
    if run.status in {RunStatus.PAUSED, RunStatus.CANCELED}:
        return
    run.status = RunStatus.RETRYING
    run.error_message = str(error_message)
    run.save(update_fields=["status", "error_message", "updated_at"])


def mark_run_paused(run_id: str, reason: str, *, record_event: bool = True) -> PipelineRun:
    run = PipelineRun.objects.get(pk=run_id)
    if run.status in {RunStatus.SUCCESS, RunStatus.ERROR, RunStatus.CANCELED}:
        return run
    run.status = RunStatus.PAUSED
    run.completed_at = timezone.now()
    run.error_message = str(reason or "Paused by admin.")
    run.save(update_fields=["status", "completed_at", "error_message", "updated_at"])
    if record_event:
        record_run_event(
            run_id,
            {
                "event": "pipeline_paused",
                "status_text": run.error_message,
            },
        )
    return run


def mark_run_canceled(run_id: str, reason: str, *, record_event: bool = True) -> PipelineRun:
    run = PipelineRun.objects.get(pk=run_id)
    if run.status == RunStatus.CANCELED:
        return run
    if run.status in {RunStatus.SUCCESS, RunStatus.ERROR}:
        return run
    run.status = RunStatus.CANCELED
    run.completed_at = timezone.now()
    run.error_message = str(reason or "Canceled by admin.")
    run.save(update_fields=["status", "completed_at", "error_message", "updated_at"])
    if record_event:
        record_run_event(
            run_id,
            {
                "event": "pipeline_canceled",
                "status_text": run.error_message,
            },
        )
    return run


def apply_category_to_run(run_id: str, category: str) -> Dict[str, Any]:
    run = PipelineRun.objects.get(pk=run_id)
    if run.status != RunStatus.SUCCESS:
        raise ValueError("Categories can only be added after a successful run.")

    rows = list(PipelineResultRow.objects.filter(run=run).values("id", "word", "row_data"))
    if not rows:
        raise ValueError("No results available for this run.")

    unique_words = sorted(
        {str(row["word"]) for row in rows if str(row.get("word", "")).strip()}
    )
    if not unique_words:
        raise ValueError("No valid words found in run results.")

    runtime = get_pipeline_runtime()
    service = PipelineRunService()
    normalized_category = service.normalize_category_name(category)

    category_df = pd.DataFrame({"word": unique_words})
    categorized_df = service.add_category_to_results(
        pipeline_db_client=runtime.pipeline_db_client,
        df_results=category_df,
        category=normalized_category,
        table_name="hanzi_processing",
    )

    category_map = {
        str(row["word"]): str(row.get("categories", ""))
        for row in categorized_df.to_dict(orient="records")
    }

    updates: List[PipelineResultRow] = []
    for row in PipelineResultRow.objects.filter(run=run):
        data = dict(row.row_data or {})
        data["categories"] = category_map.get(str(row.word), "")
        row.row_data = data
        updates.append(row)

    if updates:
        PipelineResultRow.objects.bulk_update(updates, ["row_data"])

    record_run_event(
        str(run.id),
        {
            "event": "category_applied",
            "category": normalized_category,
            "updated_rows": len(updates),
        },
    )

    return {
        "category": normalized_category,
        "updated_rows": len(updates),
    }
