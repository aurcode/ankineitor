from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from urllib.parse import urlencode

from celery import current_app
from django.contrib.auth import authenticate
from django.db.models import Count
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from loguru import logger
from rest_framework import pagination, status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from ankineitor.security.exceptions import InvalidFileError, ValidationError

from .models import (
    BackgroundJob,
    BackgroundJobStatus,
    BackgroundJobType,
    FlashcardDataset,
    GeneratedAnkiDeck,
    PipelineResultRow,
    PipelineRun,
    PipelineRunEvent,
    RunStatus,
)
from .serializers import (
    AddCategorySerializer,
    AnkiDeckGenerateSerializer,
    AuthTokenRequestSerializer,
    FlashcardCardQuerySerializer,
    FlashcardCardRerunSerializer,
    FlashcardCardUpdateSerializer,
    FlashcardDatasetFromSavedSerializer,
    GeneratedRowListQuerySerializer,
    GeneratedRowRerunSerializer,
    GeneratedRowUpdateSerializer,
    PipelineResultRowSerializer,
    PipelineRunCreateSerializer,
    PipelineRunRerunBlockSerializer,
    PipelineRunSummarySerializer,
    HIDDEN_RESULT_COLUMNS,
    WordExtractorAnalyzeSerializer,
)
from .services import (
    apply_category_to_run,
    build_pipeline_options,
    mark_run_canceled,
    mark_run_paused,
    resolve_ordered_transform_names,
)
from .tab_services import (
    cancel_background_job_for_owner,
    create_anki_background_job,
    create_flashcard_dataset_from_saved,
    create_flashcard_dataset_from_upload,
    create_word_extractor_background_job,
    get_generated_row_detail,
    get_anki_presets,
    get_background_job_events_for_owner,
    get_flashcard_card,
    rerun_flashcard_card_generation,
    rerun_generated_row_process,
    update_flashcard_card_fields,
    update_generated_row_fields,
    upload_flashcard_card_custom_image,
    upload_generated_row_custom_image,
    get_flashcard_dataset_summary,
    list_background_jobs_for_owner,
    list_flashcard_saved_files,
    list_flashcard_saved_profiles,
    resolve_flashcard_asset_path,
    resolve_background_job_csv_path,
    resolve_anki_artifact_path,
    retry_background_job_for_owner,
    serialize_background_job,
)
from .tasks import (
    run_anki_background_job_task,
    run_pipeline_task,
    run_word_extractor_background_job_task,
)


class PipelineResultsPagination(pagination.PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 200


class GeneratedRowsPagination(pagination.PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 200


MONITORED_PIPELINE_RUN_STATUSES = {
    RunStatus.QUEUED,
    RunStatus.RUNNING,
    RunStatus.RETRYING,
    RunStatus.PAUSED,
}
MONITORED_BACKGROUND_JOB_STATUSES = {
    BackgroundJobStatus.QUEUED,
    BackgroundJobStatus.RUNNING,
}
BLOCK_RERUN_DEPENDENCY_RULES = {
    "LLM Audio (Sentences)": ("LLM (Meanings/Sentences)",),
    "LLM Image Renderer (Master Prompt)": ("LLM Image Prompt (Visual Translator)",),
}


def _serialize_background_job_with_urls(job: BackgroundJob, request) -> dict:
    payload = serialize_background_job(job)
    result_payload = dict(payload.get("result_payload") or {})

    if job.job_type == BackgroundJobType.ANKI_DECK:
        artifact_id = str(result_payload.get("artifact_id", "") or "").strip()
        if artifact_id:
            result_payload["download_url"] = request.build_absolute_uri(
                reverse("anki-deck-download", kwargs={"artifact_id": artifact_id})
            )
    if str(job.csv_output_path or "").strip():
        csv_url = request.build_absolute_uri(
            reverse("background-job-results-csv", kwargs={"job_id": job.id})
        )
        payload["csv_url"] = csv_url
        result_payload.setdefault("csv_url", csv_url)
    else:
        payload["csv_url"] = None

    payload["result_payload"] = result_payload
    return payload


def _parse_uploaded_json(raw_value, field_name: str):
    if isinstance(raw_value, str):
        try:
            return json.loads(raw_value)
        except Exception as exc:
            raise ValueError(f"Invalid {field_name} JSON: {exc}")
    if isinstance(raw_value, (dict, list)):
        return raw_value
    return None


def _parse_selected_hsk_levels(request) -> list[str]:
    raw_levels = request.data.get("selected_hsk_levels", [])
    if hasattr(request.data, "getlist"):
        level_candidates = request.data.getlist("selected_hsk_levels")
        if level_candidates:
            raw_levels = level_candidates

    if isinstance(raw_levels, str):
        try:
            parsed = json.loads(raw_levels)
            if isinstance(parsed, list):
                raw_levels = parsed
            else:
                raw_levels = [raw_levels]
        except Exception:
            raw_levels = [level.strip() for level in raw_levels.split(",") if level.strip()]

    return list(raw_levels or [])


def _extract_token_from_request(request) -> str:
    query_token = str(request.query_params.get("token", "") or "").strip()
    if query_token:
        return query_token

    header = str(request.headers.get("Authorization", "") or "").strip()
    if header.lower().startswith("token "):
        return header.split(" ", 1)[1].strip()

    auth = getattr(request, "auth", None)
    auth_key = getattr(auth, "key", None)
    if auth_key:
        return str(auth_key).strip()
    if isinstance(auth, str):
        return auth.strip()
    return ""


def _resolve_user_from_token(token_key: str):
    safe_token = str(token_key or "").strip()
    if not safe_token:
        return None
    try:
        token = Token.objects.select_related("user").get(key=safe_token)
    except Token.DoesNotExist:
        return None
    return token.user


def _resolve_authenticated_user(request):
    if getattr(request, "user", None) and request.user.is_authenticated:
        return request.user
    token_key = _extract_token_from_request(request)
    return _resolve_user_from_token(token_key)


def _safe_int(value) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _safe_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _resolve_rerun_block_order(
    *,
    available_transforms: list[str],
    transform_name: str,
) -> list[str]:
    available = [str(name) for name in list(available_transforms or []) if str(name).strip()]
    if transform_name not in available:
        return []

    required = {transform_name}
    queue = [transform_name]
    while queue:
        current = queue.pop(0)
        for dependency in BLOCK_RERUN_DEPENDENCY_RULES.get(current, ()):
            if dependency in available and dependency not in required:
                required.add(dependency)
                queue.append(dependency)

    return [name for name in available if name in required]


def _serialize_celery_task(task_payload, *, scheduled: bool = False) -> dict:
    if not isinstance(task_payload, dict):
        return {
            "id": "",
            "name": "",
            "args": "",
            "kwargs": "",
            "eta": None if scheduled else "",
        }

    request_payload = task_payload.get("request")
    if not isinstance(request_payload, dict):
        request_payload = {}

    task_id = _safe_text(request_payload.get("id") or task_payload.get("id"))
    task_name = _safe_text(request_payload.get("name") or task_payload.get("name"))
    args = request_payload.get("args", task_payload.get("args", ""))
    kwargs = request_payload.get("kwargs", task_payload.get("kwargs", ""))
    eta = task_payload.get("eta")
    if eta is not None:
        eta = _safe_text(eta)

    return {
        "id": task_id,
        "name": task_name,
        "args": _safe_text(args),
        "kwargs": _safe_text(kwargs),
        "eta": eta if scheduled else "",
    }


def _collect_celery_monitor_snapshot() -> dict:
    workers = []
    totals = {
        "workers": 0,
        "active_tasks": 0,
        "reserved_tasks": 0,
        "scheduled_tasks": 0,
    }
    error_message = ""

    try:
        inspector = current_app.control.inspect(timeout=1.0)
        if inspector is None:
            return {
                "workers": workers,
                "totals": totals,
                "error": "Celery inspector is unavailable.",
            }
        active_tasks = inspector.active() or {}
        reserved_tasks = inspector.reserved() or {}
        scheduled_tasks = inspector.scheduled() or {}
        active_queues = inspector.active_queues() or {}
        worker_stats = inspector.stats() or {}
    except Exception as exc:
        return {
            "workers": workers,
            "totals": totals,
            "error": str(exc),
        }

    worker_names = sorted(
        set(active_tasks.keys())
        | set(reserved_tasks.keys())
        | set(scheduled_tasks.keys())
        | set(active_queues.keys())
    )
    for worker_name in worker_names:
        worker_active_tasks = [
            _serialize_celery_task(item)
            for item in list(active_tasks.get(worker_name) or [])
        ]
        worker_reserved_tasks = [
            _serialize_celery_task(item)
            for item in list(reserved_tasks.get(worker_name) or [])
        ]
        worker_scheduled_tasks = [
            _serialize_celery_task(item, scheduled=True)
            for item in list(scheduled_tasks.get(worker_name) or [])
        ]

        queue_rows = list(active_queues.get(worker_name) or [])
        queue_names = sorted(
            {
                _safe_text(queue_row.get("name"))
                for queue_row in queue_rows
                if isinstance(queue_row, dict) and _safe_text(queue_row.get("name"))
            }
        )

        stats_row = worker_stats.get(worker_name) if isinstance(worker_stats, dict) else None
        max_concurrency = None
        if isinstance(stats_row, dict):
            pool_row = stats_row.get("pool")
            if isinstance(pool_row, dict):
                max_concurrency = pool_row.get("max-concurrency")

        workers.append(
            {
                "worker_name": worker_name,
                "queues": queue_names,
                "max_concurrency": _safe_int(max_concurrency),
                "active_count": len(worker_active_tasks),
                "reserved_count": len(worker_reserved_tasks),
                "scheduled_count": len(worker_scheduled_tasks),
                "active_tasks": worker_active_tasks,
                "reserved_tasks": worker_reserved_tasks,
                "scheduled_tasks": worker_scheduled_tasks,
            }
        )
        totals["active_tasks"] += len(worker_active_tasks)
        totals["reserved_tasks"] += len(worker_reserved_tasks)
        totals["scheduled_tasks"] += len(worker_scheduled_tasks)

    totals["workers"] = len(workers)
    return {
        "workers": workers,
        "totals": totals,
        "error": error_message,
    }


def _latest_pipeline_events_by_run(run_ids: list[str]) -> dict[str, PipelineRunEvent]:
    if not run_ids:
        return {}

    event_by_run: dict[str, PipelineRunEvent] = {}
    queryset = PipelineRunEvent.objects.filter(run_id__in=run_ids).order_by("run_id", "-sequence")
    for event in queryset:
        run_id = str(event.run_id)
        if run_id not in event_by_run:
            event_by_run[run_id] = event
    return event_by_run


def _build_flashcard_asset_url(request, path_value: str) -> str:
    raw_path = str(path_value or "").strip()
    if not raw_path:
        return ""
    lowered = raw_path.lower()
    if lowered.startswith(("http://", "https://", "data:")):
        return raw_path

    try:
        resolve_flashcard_asset_path(raw_path)
    except ValueError:
        return ""

    query = {"path": raw_path}
    token_key = _extract_token_from_request(request)
    if token_key:
        query["token"] = token_key
    # Keep asset URLs origin-relative so the frontend proxy (Vite/Caddy) can
    # route media requests correctly in Docker setups.
    return f"{reverse('flashcards-asset')}?{urlencode(query)}"


def _attach_flashcard_media_urls(payload: dict, request) -> dict:
    normalized = dict(payload or {})

    front = dict(normalized.get("front") or {})
    front_audio = str(front.get("audio", "") or "").strip()
    if front_audio:
        front_audio_url = _build_flashcard_asset_url(request, front_audio)
        if front_audio_url:
            front["audio"] = front_audio_url
    normalized["front"] = front

    back = dict(normalized.get("back") or {})

    sentence_rows = list(back.get("sentences") or [])
    normalized_sentences = []
    for sentence in sentence_rows:
        sentence_payload = dict(sentence or {})
        sentence_audio = str(sentence_payload.get("audio", "") or "").strip()
        if sentence_audio:
            sentence_audio_url = _build_flashcard_asset_url(request, sentence_audio)
            if sentence_audio_url:
                sentence_payload["audio"] = sentence_audio_url
        normalized_sentences.append(sentence_payload)
    back["sentences"] = normalized_sentences

    image_payload = dict(back.get("image") or {})
    picture_path = str(image_payload.get("picture", "") or "").strip()
    if picture_path:
        picture_url = _build_flashcard_asset_url(request, picture_path)
        if picture_url:
            image_payload["picture"] = picture_url
            image_payload["picture_url"] = picture_url
        elif picture_path.lower().startswith(("http://", "https://", "data:")):
            image_payload["picture_url"] = picture_path
    back["image"] = image_payload

    normalized["back"] = back
    return normalized


def _attach_generated_row_media_urls(payload: dict, request) -> dict:
    normalized = dict(payload or {})
    row_data = dict(normalized.get("row_data") or {})

    for key, value in list(row_data.items()):
        raw_value = str(value or "").strip()
        if not raw_value:
            continue

        is_audio_field = key == "audio" or (key.startswith("sentence_") and key.endswith("_audio"))
        if is_audio_field:
            audio_url = _build_flashcard_asset_url(request, raw_value)
            if audio_url:
                row_data[key] = audio_url
            continue

        if key == "picture":
            picture_url = _build_flashcard_asset_url(request, raw_value)
            if picture_url:
                row_data["picture"] = picture_url
                row_data["picture_url"] = picture_url
            elif raw_value.lower().startswith(("http://", "https://", "data:")):
                row_data["picture_url"] = raw_value

    normalized["row_data"] = row_data
    card_payload = normalized.get("card")
    if isinstance(card_payload, dict):
        normalized["card"] = _attach_flashcard_media_urls(card_payload, request)
    return normalized


def _serialize_generated_row_summary(row: PipelineResultRow, request) -> dict:
    row_data = dict(row.row_data or {})
    profile_id = _safe_text(row_data.get("profile_id")) or _safe_text(row.run.profile_id)
    picture = _safe_text(row_data.get("picture"))
    picture_url = _build_flashcard_asset_url(request, picture) if picture else ""
    if picture_url:
        picture = picture_url

    payload = {
        "row_id": int(row.id),
        "run_id": str(row.run_id),
        "run_status": row.run.status,
        "profile_id": profile_id,
        "row_index": int(row.row_index or 0),
        "word": _safe_text(row.word),
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "meaning_english": _safe_text(row_data.get("meaning_english"))
        or _safe_text(row_data.get("detailed_explanation_english")),
        "meaning_spanish": _safe_text(row_data.get("meaning_spanish"))
        or _safe_text(row_data.get("detailed_explanation_spanish")),
        "picture": picture,
        "picture_url": picture,
        "image_render_status": _safe_text(row_data.get("image_render_status")),
    }
    return payload


class AuthTokenView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = AuthTokenRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = authenticate(
            request=request,
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            return Response(
                {"detail": "Invalid username or password."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not user.is_active:
            return Response(
                {"detail": "User account is inactive."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {
                "token": token.key,
                "user": {
                    "id": user.id,
                    "username": user.get_username(),
                },
            }
        )


class PipelineOptionsView(APIView):
    def get(self, request):
        del request
        return Response(build_pipeline_options())


class AdminQueueMonitorView(APIView):
    def get(self, request):
        if not (request.user.is_staff or request.user.is_superuser):
            return Response(
                {"detail": "Admin access required."},
                status=status.HTTP_403_FORBIDDEN,
            )

        pipeline_runs = list(
            PipelineRun.objects.select_related("owner")
            .filter(status__in=MONITORED_PIPELINE_RUN_STATUSES)
            .order_by("created_at")[:200]
        )
        pipeline_run_ids = [str(run.id) for run in pipeline_runs]
        latest_events = _latest_pipeline_events_by_run(pipeline_run_ids)

        pipeline_runs_payload = []
        for run in pipeline_runs:
            latest_event = latest_events.get(str(run.id))
            latest_payload = dict(latest_event.payload or {}) if latest_event else {}
            pipeline_runs_payload.append(
                {
                    "id": str(run.id),
                    "owner_username": run.owner.get_username() if run.owner_id else "",
                    "status": run.status,
                    "profile_id": run.profile_id,
                    "source_language": run.source_language,
                    "total_input_words": int(run.total_input_words or 0),
                    "celery_task_id": run.celery_task_id,
                    "current_transform": _safe_text(
                        latest_payload.get("transform_name") or latest_payload.get("step")
                    ),
                    "current_word": _safe_text(latest_payload.get("current_word")),
                    "words_left": _safe_int(latest_payload.get("words_left")),
                    "running_count": _safe_int(latest_payload.get("running_count")),
                    "queued_count": _safe_int(latest_payload.get("queued_count")),
                    "last_event_type": latest_event.event_type if latest_event else "",
                    "last_event_sequence": _safe_int(
                        latest_event.sequence if latest_event else 0
                    ),
                    "last_event_at": (
                        latest_event.created_at.isoformat() if latest_event else None
                    ),
                    "created_at": run.created_at.isoformat() if run.created_at else None,
                    "started_at": run.started_at.isoformat() if run.started_at else None,
                    "updated_at": run.updated_at.isoformat() if run.updated_at else None,
                }
            )

        background_jobs = list(
            BackgroundJob.objects.select_related("owner")
            .filter(status__in=MONITORED_BACKGROUND_JOB_STATUSES)
            .order_by("created_at")[:200]
        )
        background_jobs_payload = [
            {
                "id": str(job.id),
                "owner_username": job.owner.get_username() if job.owner_id else "",
                "job_type": job.job_type,
                "status": job.status,
                "progress_ratio": float(job.progress_ratio or 0.0),
                "status_text": job.status_text,
                "celery_task_id": job.celery_task_id,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "updated_at": job.updated_at.isoformat() if job.updated_at else None,
            }
            for job in background_jobs
        ]

        celery_snapshot = _collect_celery_monitor_snapshot()
        celery_totals = dict(celery_snapshot.get("totals") or {})

        return Response(
            {
                "generated_at": timezone.now().isoformat(),
                "summary": {
                    "active_pipeline_runs": len(pipeline_runs_payload),
                    "active_background_jobs": len(background_jobs_payload),
                    "celery_workers": _safe_int(celery_totals.get("workers")),
                    "celery_active_tasks": _safe_int(celery_totals.get("active_tasks")),
                    "celery_reserved_tasks": _safe_int(celery_totals.get("reserved_tasks")),
                    "celery_scheduled_tasks": _safe_int(celery_totals.get("scheduled_tasks")),
                },
                "pipeline_runs": pipeline_runs_payload,
                "background_jobs": background_jobs_payload,
                "celery": celery_snapshot,
            }
        )


class AdminPipelineRunPauseView(APIView):
    def post(self, request, run_id: str):
        if not (request.user.is_staff or request.user.is_superuser):
            return Response(
                {"detail": "Admin access required."},
                status=status.HTTP_403_FORBIDDEN,
            )

        run = get_object_or_404(PipelineRun, pk=run_id)
        if run.status in {RunStatus.SUCCESS, RunStatus.ERROR, RunStatus.CANCELED}:
            return Response(
                {"detail": "Only queued/running/retrying runs can be paused."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if run.status == RunStatus.PAUSED:
            return Response({"run": PipelineRunSummarySerializer(run).data})

        if run.celery_task_id:
            try:
                current_app.control.revoke(run.celery_task_id, terminate=False)
            except Exception:
                pass

        actor = request.user.get_username() if request.user and request.user.is_authenticated else ""
        reason = f"Paused by admin {actor}."
        updated = mark_run_paused(str(run.id), reason, record_event=True)
        return Response({"run": PipelineRunSummarySerializer(updated).data})


class AdminPipelineRunCancelView(APIView):
    def post(self, request, run_id: str):
        if not (request.user.is_staff or request.user.is_superuser):
            return Response(
                {"detail": "Admin access required."},
                status=status.HTTP_403_FORBIDDEN,
            )

        run = get_object_or_404(PipelineRun, pk=run_id)
        if run.status in {RunStatus.SUCCESS, RunStatus.ERROR}:
            return Response(
                {"detail": "Completed or failed runs cannot be canceled."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if run.status == RunStatus.CANCELED:
            return Response({"run": PipelineRunSummarySerializer(run).data})

        if run.celery_task_id:
            try:
                current_app.control.revoke(run.celery_task_id, terminate=False)
            except Exception:
                pass

        actor = request.user.get_username() if request.user and request.user.is_authenticated else ""
        reason = f"Canceled by admin {actor}."
        updated = mark_run_canceled(str(run.id), reason, record_event=True)
        return Response({"run": PipelineRunSummarySerializer(updated).data})


class AdminPipelineRunResumeView(APIView):
    def post(self, request, run_id: str):
        if not (request.user.is_staff or request.user.is_superuser):
            return Response(
                {"detail": "Admin access required."},
                status=status.HTTP_403_FORBIDDEN,
            )

        run = get_object_or_404(PipelineRun, pk=run_id)
        if run.status != RunStatus.PAUSED:
            return Response(
                {"detail": "Only paused runs can be resumed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        run.status = RunStatus.QUEUED
        run.completed_at = None
        run.started_at = None
        run.error_message = ""
        run.save(update_fields=["status", "completed_at", "started_at", "error_message", "updated_at"])

        task = run_pipeline_task.delay(str(run.id))
        run.celery_task_id = str(task.id)
        run.save(update_fields=["celery_task_id", "updated_at"])
        return Response({"run": PipelineRunSummarySerializer(run).data})


class PipelineRunCreateView(APIView):
    def get(self, request):
        raw_status = str(request.query_params.get("status", "") or "").strip().lower()
        raw_profile_id = str(request.query_params.get("profile_id", "") or "").strip()
        try:
            limit = int(request.query_params.get("limit", 20) or 20)
        except Exception:
            return Response({"detail": "limit must be an integer."}, status=status.HTTP_400_BAD_REQUEST)
        safe_limit = max(1, min(limit, 200))

        queryset = PipelineRun.objects.filter(owner=request.user)
        if raw_status:
            allowed_statuses = {choice for choice, _label in RunStatus.choices}
            if raw_status not in allowed_statuses:
                return Response(
                    {
                        "detail": "status must be one of: queued, running, retrying, paused, canceled, success, error."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            queryset = queryset.filter(status=raw_status)
        if raw_profile_id:
            queryset = queryset.filter(profile_id=raw_profile_id)

        queryset = queryset.annotate(event_count=Count("events")).order_by("-created_at")[:safe_limit]
        return Response({"runs": PipelineRunSummarySerializer(queryset, many=True).data})

    def post(self, request):
        serializer = PipelineRunCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        profile_id = payload["profile_id"]
        requested_transforms = list(payload.get("transform_names") or [])
        words = list(payload["words"])

        try:
            selected_transform_names, ordered_transform_names, source_language = (
                resolve_ordered_transform_names(
                    profile_id=profile_id,
                    selected_transform_names=requested_transforms,
                )
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        run = PipelineRun.objects.create(
            owner=request.user,
            profile_id=profile_id,
            source_language=source_language,
            selected_transform_names=selected_transform_names,
            ordered_transform_names=ordered_transform_names,
            input_words=words,
            total_input_words=len(words),
        )

        task = run_pipeline_task.delay(str(run.id))
        run.celery_task_id = str(task.id)
        run.save(update_fields=["celery_task_id", "updated_at"])

        return Response(PipelineRunSummarySerializer(run).data, status=status.HTTP_201_CREATED)


class PipelineRunDetailView(APIView):
    def get(self, request, run_id: str):
        run = get_object_or_404(PipelineRun, pk=run_id, owner=request.user)
        return Response(PipelineRunSummarySerializer(run).data)


class PipelineRunRerunBlockView(APIView):
    def post(self, request, run_id: str):
        source_run = get_object_or_404(PipelineRun, pk=run_id, owner=request.user)
        serializer = PipelineRunRerunBlockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        transform_name = str(serializer.validated_data["transform_name"]).strip()
        if not transform_name:
            return Response(
                {"detail": "transform_name is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if transform_name not in list(source_run.ordered_transform_names or []):
            return Response(
                {"detail": f"Unknown transform '{transform_name}' for this run."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        words = list(source_run.input_words or [])
        if not words:
            return Response(
                {"detail": "Selected run has no input words to rerun."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ordered_transform_names = _resolve_rerun_block_order(
            available_transforms=list(source_run.ordered_transform_names or []),
            transform_name=transform_name,
        )
        if not ordered_transform_names:
            return Response(
                {"detail": f"Unable to build rerun order for transform '{transform_name}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        selected_transform_names = [transform_name]

        rerun = PipelineRun.objects.create(
            owner=request.user,
            profile_id=source_run.profile_id,
            source_language=source_run.source_language,
            selected_transform_names=selected_transform_names,
            ordered_transform_names=ordered_transform_names,
            input_words=words,
            total_input_words=len(words),
        )

        task = run_pipeline_task.delay(str(rerun.id))
        rerun.celery_task_id = str(task.id)
        rerun.save(update_fields=["celery_task_id", "updated_at"])

        return Response(PipelineRunSummarySerializer(rerun).data, status=status.HTTP_201_CREATED)


class PipelineRunResultsView(APIView):
    pagination_class = PipelineResultsPagination

    def get(self, request, run_id: str):
        run = get_object_or_404(PipelineRun, pk=run_id, owner=request.user)
        queryset = PipelineResultRow.objects.filter(run=run)

        search_term = str(request.query_params.get("search", "") or "").strip()
        if search_term:
            queryset = queryset.filter(word__icontains=search_term)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)
        serializer = PipelineResultRowSerializer(page, many=True)

        first_row = queryset.first()
        columns = []
        if first_row and isinstance(first_row.row_data, dict):
            columns = [
                str(column)
                for column in first_row.row_data.keys()
                if str(column) not in HIDDEN_RESULT_COLUMNS
            ]
        if "timestamp" not in columns:
            columns.append("timestamp")

        csv_url = None
        if run.csv_output_path:
            csv_url = request.build_absolute_uri(
                reverse("pipeline-run-results-csv", kwargs={"run_id": run.id})
            )

        return Response(
            {
                "run_id": str(run.id),
                "status": run.status,
                "columns": columns,
                "csv_url": csv_url,
                "count": paginator.page.paginator.count,
                "next": paginator.get_next_link(),
                "previous": paginator.get_previous_link(),
                "results": serializer.data,
            }
        )


class PipelineRunResultsCsvView(APIView):
    def get(self, request, run_id: str):
        run = get_object_or_404(PipelineRun, pk=run_id, owner=request.user)
        if not run.csv_output_path:
            raise Http404("CSV output is not available for this run.")

        csv_path = Path(run.csv_output_path)
        if not csv_path.is_absolute():
            csv_path = Path.cwd() / csv_path
        csv_path = csv_path.resolve()

        allowed_base = Path.cwd().resolve()
        if allowed_base not in csv_path.parents:
            return Response(
                {"detail": "CSV path is outside the allowed workspace."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not csv_path.exists() or not csv_path.is_file():
            raise Http404("CSV file not found.")

        return FileResponse(
            open(csv_path, "rb"),
            as_attachment=True,
            filename=run.csv_download_name or csv_path.name,
            content_type="text/csv",
        )


class PipelineRunAddCategoryView(APIView):
    def post(self, request, run_id: str):
        run = get_object_or_404(PipelineRun, pk=run_id, owner=request.user)
        serializer = AddCategorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        category = serializer.validated_data["category"]
        try:
            result = apply_category_to_run(str(run.id), category)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        run.refresh_from_db()
        return Response(
            {
                "run": PipelineRunSummarySerializer(run).data,
                "category": result["category"],
                "updated_rows": result["updated_rows"],
            }
        )


class GeneratedRowListView(APIView):
    pagination_class = GeneratedRowsPagination

    def get(self, request):
        serializer = GeneratedRowListQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        filters = serializer.validated_data

        queryset = PipelineResultRow.objects.filter(run__owner=request.user).select_related("run")
        search_term = _safe_text(filters.get("search"))
        if search_term:
            queryset = queryset.filter(word__icontains=search_term)

        profile_id = _safe_text(filters.get("profile_id"))
        if profile_id:
            queryset = queryset.filter(run__profile_id=profile_id)

        run_id = filters.get("run_id")
        if run_id:
            queryset = queryset.filter(run_id=run_id)

        queryset = queryset.order_by("-created_at", "-id")

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)
        results = [_serialize_generated_row_summary(row, request) for row in page]
        return Response(
            {
                "count": paginator.page.paginator.count,
                "next": paginator.get_next_link(),
                "previous": paginator.get_previous_link(),
                "results": results,
            }
        )


class GeneratedRowDetailView(APIView):
    def get(self, request, row_id: int):
        row = get_object_or_404(PipelineResultRow.objects.select_related("run"), pk=row_id, run__owner=request.user)
        payload = get_generated_row_detail(row_id=int(row.id), owner=request.user)
        return Response({"row": _attach_generated_row_media_urls(payload, request)})


class GeneratedRowUpdateView(APIView):
    def post(self, request, row_id: int):
        serializer = GeneratedRowUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        row = get_object_or_404(PipelineResultRow.objects.select_related("run"), pk=row_id, run__owner=request.user)
        try:
            payload = update_generated_row_fields(
                row_id=int(row.id),
                owner=request.user,
                updates=serializer.validated_data["updates"],
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"row": _attach_generated_row_media_urls(payload, request)})


class GeneratedRowRerunView(APIView):
    def post(self, request, row_id: int):
        serializer = GeneratedRowRerunSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        row = get_object_or_404(PipelineResultRow.objects.select_related("run"), pk=row_id, run__owner=request.user)
        try:
            payload = rerun_generated_row_process(
                row_id=int(row.id),
                owner=request.user,
                process=serializer.validated_data["process"],
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.exception("Failed to rerun generated row {} process: {}", row_id, exc)
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "row": _attach_generated_row_media_urls(payload, request),
                "rerun_process": payload.get("rerun_process", ""),
                "applied_transforms": payload.get("applied_transforms", []),
            }
        )


class GeneratedRowImageUploadView(APIView):
    def post(self, request, row_id: int):
        image_file = request.FILES.get("image_file")
        if image_file is None:
            return Response(
                {"detail": "image_file is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        row = get_object_or_404(PipelineResultRow.objects.select_related("run"), pk=row_id, run__owner=request.user)
        try:
            payload = upload_generated_row_custom_image(
                row_id=int(row.id),
                owner=request.user,
                file_name=image_file.name,
                file_bytes=image_file.read(),
            )
        except (ValueError, ValidationError, InvalidFileError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"row": _attach_generated_row_media_urls(payload, request)})


class AnkiPresetsView(APIView):
    def get(self, request):
        del request
        return Response(get_anki_presets())


class AnkiDeckGenerateView(APIView):
    def post(self, request):
        uploaded_csv = request.FILES.get("csv_file")
        if uploaded_csv is None:
            return Response(
                {"detail": "csv_file is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            parsed_config = _parse_uploaded_json(request.data.get("config"), "config")
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        serializer = AnkiDeckGenerateSerializer(
            data={
                "deck_name": request.data.get("deck_name", ""),
                "config": parsed_config,
            }
        )
        serializer.is_valid(raise_exception=True)

        try:
            job = create_anki_background_job(
                owner=request.user,
                csv_name=uploaded_csv.name,
                csv_bytes=uploaded_csv.read(),
                deck_name=serializer.validated_data["deck_name"],
                config_payload=serializer.validated_data["config"],
            )
        except (ValueError, RuntimeError, ValidationError, InvalidFileError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        task = run_anki_background_job_task.delay(str(job.id))
        job.celery_task_id = str(task.id)
        job.save(update_fields=["celery_task_id", "updated_at"])

        return Response(
            {
                "job": _serialize_background_job_with_urls(job, request),
                "events": get_background_job_events_for_owner(owner=request.user, job_id=str(job.id)),
            },
            status=status.HTTP_202_ACCEPTED,
        )


class BackgroundJobListView(APIView):
    def get(self, request):
        raw_job_type = str(request.query_params.get("job_type", "") or "").strip().lower()
        job_type = raw_job_type or None
        if job_type and job_type not in {BackgroundJobType.ANKI_DECK, BackgroundJobType.WORD_EXTRACTOR}:
            return Response(
                {"detail": "job_type must be one of: anki_deck, word_extractor."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            limit = int(request.query_params.get("limit", 20) or 20)
        except Exception:
            return Response({"detail": "limit must be an integer."}, status=status.HTTP_400_BAD_REQUEST)

        jobs = list_background_jobs_for_owner(
            owner=request.user,
            job_type=job_type,
            limit=limit,
        )
        return Response({"jobs": [_serialize_background_job_with_urls(job, request) for job in jobs]})


class BackgroundJobDetailView(APIView):
    def get(self, request, job_id: str):
        job = get_object_or_404(BackgroundJob, pk=job_id, owner=request.user)
        return Response({"job": _serialize_background_job_with_urls(job, request)})


class BackgroundJobCancelView(APIView):
    def post(self, request, job_id: str):
        try:
            job = cancel_background_job_for_owner(owner=request.user, job_id=job_id)
        except BackgroundJob.DoesNotExist:
            raise Http404("Job not found.")

        if job.celery_task_id and job.status == BackgroundJobStatus.CANCELED:
            try:
                current_app.control.revoke(job.celery_task_id, terminate=False)
            except Exception:
                pass

        return Response({"job": _serialize_background_job_with_urls(job, request)})


class BackgroundJobRetryView(APIView):
    def post(self, request, job_id: str):
        try:
            job = retry_background_job_for_owner(owner=request.user, job_id=job_id)
        except BackgroundJob.DoesNotExist:
            raise Http404("Job not found.")
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if job.job_type == BackgroundJobType.ANKI_DECK:
            task = run_anki_background_job_task.delay(str(job.id))
        elif job.job_type == BackgroundJobType.WORD_EXTRACTOR:
            task = run_word_extractor_background_job_task.delay(str(job.id))
        else:
            return Response(
                {"detail": f"Unsupported job type '{job.job_type}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        job.celery_task_id = str(task.id)
        job.save(update_fields=["celery_task_id", "updated_at"])

        return Response(
            {
                "job": _serialize_background_job_with_urls(job, request),
                "events": get_background_job_events_for_owner(owner=request.user, job_id=str(job.id)),
            },
            status=status.HTTP_202_ACCEPTED,
        )


class BackgroundJobEventsView(APIView):
    def get(self, request, job_id: str):
        get_object_or_404(BackgroundJob, pk=job_id, owner=request.user)
        return Response(
            {
                "job_id": job_id,
                "events": get_background_job_events_for_owner(owner=request.user, job_id=job_id),
            }
        )


class BackgroundJobResultsCsvView(APIView):
    def get(self, request, job_id: str):
        job = get_object_or_404(BackgroundJob, pk=job_id, owner=request.user)

        try:
            csv_path = resolve_background_job_csv_path(job)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        if not csv_path.exists() or not csv_path.is_file():
            raise Http404("CSV file not found.")

        return FileResponse(
            open(csv_path, "rb"),
            as_attachment=True,
            filename=job.csv_download_name or csv_path.name,
            content_type="text/csv",
        )


class AnkiDeckDownloadView(APIView):
    def get(self, request, artifact_id: str):
        artifact = get_object_or_404(GeneratedAnkiDeck, pk=artifact_id, owner=request.user)
        try:
            deck_path = resolve_anki_artifact_path(artifact)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)

        if not deck_path.exists() or not deck_path.is_file():
            raise Http404("Deck file not found.")

        return FileResponse(
            open(deck_path, "rb"),
            as_attachment=True,
            filename=deck_path.name,
            content_type="application/octet-stream",
        )


class FlashcardSavedProfilesView(APIView):
    def get(self, request):
        del request
        profiles = list_flashcard_saved_profiles()
        return Response({"profiles": profiles})


class FlashcardSavedFilesView(APIView):
    def get(self, request):
        profile_id = str(request.query_params.get("profile_id", "") or "").strip()
        if not profile_id:
            return Response(
                {"detail": "profile_id query parameter is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            files = list_flashcard_saved_files(profile_id)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"profile_id": profile_id, "files": files})


class FlashcardDatasetFromSavedView(APIView):
    def post(self, request):
        serializer = FlashcardDatasetFromSavedSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            payload = create_flashcard_dataset_from_saved(
                owner=request.user,
                profile_id=serializer.validated_data["profile_id"],
                file_name=serializer.validated_data.get("file_name"),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(payload, status=status.HTTP_201_CREATED)


class FlashcardDatasetUploadView(APIView):
    def post(self, request):
        uploaded_csv = request.FILES.get("csv_file")
        if uploaded_csv is None:
            return Response(
                {"detail": "csv_file is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payload = create_flashcard_dataset_from_upload(
                owner=request.user,
                file_name=uploaded_csv.name,
                file_bytes=uploaded_csv.read(),
            )
        except (ValueError, ValidationError, InvalidFileError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(payload, status=status.HTTP_201_CREATED)


class FlashcardDatasetSummaryView(APIView):
    def get(self, request, dataset_id: str):
        dataset = get_object_or_404(FlashcardDataset, pk=dataset_id, owner=request.user)
        payload = get_flashcard_dataset_summary(str(dataset.id), owner=request.user)
        return Response(payload)


class FlashcardDatasetCardView(APIView):
    def get(self, request, dataset_id: str):
        serializer = FlashcardCardQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        dataset = get_object_or_404(FlashcardDataset, pk=dataset_id, owner=request.user)
        try:
            payload = get_flashcard_card(
                dataset_id=str(dataset.id),
                owner=request.user,
                index=serializer.validated_data["index"],
                profile_filter=serializer.validated_data.get("profile_filter"),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(_attach_flashcard_media_urls(payload, request))


class FlashcardDatasetCardUpdateView(APIView):
    def post(self, request, dataset_id: str):
        serializer = FlashcardCardUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        dataset = get_object_or_404(FlashcardDataset, pk=dataset_id, owner=request.user)
        try:
            payload = update_flashcard_card_fields(
                dataset_id=str(dataset.id),
                owner=request.user,
                index=serializer.validated_data["index"],
                profile_filter=serializer.validated_data.get("profile_filter"),
                updates=serializer.validated_data["updates"],
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "dataset": payload["dataset"],
                "card": _attach_flashcard_media_urls(payload["card"], request),
            }
        )


class FlashcardDatasetCardRerunView(APIView):
    def post(self, request, dataset_id: str):
        serializer = FlashcardCardRerunSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        dataset = get_object_or_404(FlashcardDataset, pk=dataset_id, owner=request.user)
        try:
            payload = rerun_flashcard_card_generation(
                dataset_id=str(dataset.id),
                owner=request.user,
                index=serializer.validated_data["index"],
                profile_filter=serializer.validated_data.get("profile_filter"),
                mode=serializer.validated_data["mode"],
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.exception("Failed to rerun card generation for dataset {}: {}", dataset_id, exc)
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "dataset": payload["dataset"],
                "card": _attach_flashcard_media_urls(payload["card"], request),
                "rerun_mode": payload.get("rerun_mode", ""),
                "applied_transforms": payload.get("applied_transforms", []),
            }
        )


class FlashcardDatasetCardImageUploadView(APIView):
    def post(self, request, dataset_id: str):
        serializer = FlashcardCardQuerySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        image_file = request.FILES.get("image_file")
        if image_file is None:
            return Response(
                {"detail": "image_file is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        dataset = get_object_or_404(FlashcardDataset, pk=dataset_id, owner=request.user)
        try:
            payload = upload_flashcard_card_custom_image(
                dataset_id=str(dataset.id),
                owner=request.user,
                index=serializer.validated_data["index"],
                profile_filter=serializer.validated_data.get("profile_filter"),
                file_name=image_file.name,
                file_bytes=image_file.read(),
            )
        except (ValueError, ValidationError, InvalidFileError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "dataset": payload["dataset"],
                "card": _attach_flashcard_media_urls(payload["card"], request),
            }
        )


class FlashcardAssetView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        user = _resolve_authenticated_user(request)
        if user is None or not user.is_authenticated:
            return Response(
                {"detail": "Authentication credentials were not provided."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        raw_path = str(request.query_params.get("path", "") or "").strip()
        if not raw_path:
            return Response(
                {"detail": "path query parameter is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            asset_path = resolve_flashcard_asset_path(raw_path)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)

        if not asset_path.exists() or not asset_path.is_file():
            raise Http404("Asset file not found.")

        content_type, _encoding = mimetypes.guess_type(asset_path.name)
        return FileResponse(
            open(asset_path, "rb"),
            as_attachment=False,
            filename=asset_path.name,
            content_type=content_type or "application/octet-stream",
        )


class WordExtractorAnalyzeView(APIView):
    def post(self, request):
        serializer = WordExtractorAnalyzeSerializer(
            data={
                "text_input": request.data.get("text_input", ""),
                "selected_hsk_levels": _parse_selected_hsk_levels(request),
                "min_frequency": request.data.get("min_frequency", 2),
            }
        )
        serializer.is_valid(raise_exception=True)

        uploaded_files = []
        for uploaded in request.FILES.getlist("files"):
            uploaded_files.append((uploaded.name, uploaded.read()))

        try:
            job = create_word_extractor_background_job(
                owner=request.user,
                uploaded_files=uploaded_files,
                text_input=serializer.validated_data["text_input"],
                selected_hsk_levels=serializer.validated_data["selected_hsk_levels"],
                min_frequency=serializer.validated_data["min_frequency"],
            )
        except (ValueError, RuntimeError, ValidationError, InvalidFileError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        task = run_word_extractor_background_job_task.delay(str(job.id))
        job.celery_task_id = str(task.id)
        job.save(update_fields=["celery_task_id", "updated_at"])

        return Response(
            {
                "job": _serialize_background_job_with_urls(job, request),
                "events": get_background_job_events_for_owner(owner=request.user, job_id=str(job.id)),
            },
            status=status.HTTP_202_ACCEPTED,
        )
