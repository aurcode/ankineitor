from __future__ import annotations

import json
from pathlib import Path

from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse
from rest_framework import pagination, status
from rest_framework.response import Response
from rest_framework.views import APIView

from ankineitor.security.exceptions import InvalidFileError, ValidationError

from .models import FlashcardDataset, GeneratedAnkiDeck, PipelineResultRow, PipelineRun
from .serializers import (
    AddCategorySerializer,
    AnkiDeckGenerateSerializer,
    FlashcardCardQuerySerializer,
    FlashcardDatasetFromSavedSerializer,
    PipelineResultRowSerializer,
    PipelineRunCreateSerializer,
    PipelineRunSummarySerializer,
    WordExtractorAnalyzeSerializer,
)
from .services import apply_category_to_run, build_pipeline_options, resolve_ordered_transform_names
from .tab_services import (
    analyze_word_extractor,
    create_flashcard_dataset_from_saved,
    create_flashcard_dataset_from_upload,
    generate_anki_deck_artifact,
    get_anki_presets,
    get_flashcard_card,
    get_flashcard_dataset_summary,
    list_flashcard_saved_files,
    list_flashcard_saved_profiles,
    resolve_anki_artifact_path,
)
from .tasks import run_pipeline_task


class PipelineResultsPagination(pagination.PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 200


class PipelineOptionsView(APIView):
    def get(self, request):
        del request
        return Response(build_pipeline_options())


class PipelineRunCreateView(APIView):
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
        del request
        run = get_object_or_404(PipelineRun, pk=run_id)
        return Response(PipelineRunSummarySerializer(run).data)


class PipelineRunResultsView(APIView):
    pagination_class = PipelineResultsPagination

    def get(self, request, run_id: str):
        run = get_object_or_404(PipelineRun, pk=run_id)
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
            columns = list(first_row.row_data.keys())

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
        del request
        run = get_object_or_404(PipelineRun, pk=run_id)
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
        run = get_object_or_404(PipelineRun, pk=run_id)
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

        raw_config = request.data.get("config")
        if isinstance(raw_config, str):
            try:
                parsed_config = json.loads(raw_config)
            except Exception as exc:
                return Response(
                    {"detail": f"Invalid config JSON: {exc}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        elif isinstance(raw_config, dict):
            parsed_config = raw_config
        else:
            parsed_config = None

        serializer = AnkiDeckGenerateSerializer(
            data={
                "deck_name": request.data.get("deck_name", ""),
                "config": parsed_config,
            }
        )
        serializer.is_valid(raise_exception=True)

        try:
            artifact = generate_anki_deck_artifact(
                csv_name=uploaded_csv.name,
                csv_bytes=uploaded_csv.read(),
                deck_name=serializer.validated_data["deck_name"],
                config_payload=serializer.validated_data["config"],
            )
        except (ValueError, RuntimeError, ValidationError, InvalidFileError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "artifact_id": str(artifact.id),
                "deck_name": artifact.deck_name,
                "source_csv_name": artifact.source_csv_name,
                "file_size_bytes": artifact.file_size_bytes,
                "download_url": request.build_absolute_uri(
                    reverse("anki-deck-download", kwargs={"artifact_id": artifact.id})
                ),
                "created_at": artifact.created_at.isoformat(),
            },
            status=status.HTTP_201_CREATED,
        )


class AnkiDeckDownloadView(APIView):
    def get(self, request, artifact_id: str):
        del request
        artifact = get_object_or_404(GeneratedAnkiDeck, pk=artifact_id)
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
                file_name=uploaded_csv.name,
                file_bytes=uploaded_csv.read(),
            )
        except (ValueError, ValidationError, InvalidFileError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(payload, status=status.HTTP_201_CREATED)


class FlashcardDatasetSummaryView(APIView):
    def get(self, request, dataset_id: str):
        del request
        dataset = get_object_or_404(FlashcardDataset, pk=dataset_id)
        payload = get_flashcard_dataset_summary(str(dataset.id))
        return Response(payload)


class FlashcardDatasetCardView(APIView):
    def get(self, request, dataset_id: str):
        serializer = FlashcardCardQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        dataset = get_object_or_404(FlashcardDataset, pk=dataset_id)
        try:
            payload = get_flashcard_card(
                dataset_id=str(dataset.id),
                index=serializer.validated_data["index"],
                profile_filter=serializer.validated_data.get("profile_filter"),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(payload)


class WordExtractorAnalyzeView(APIView):
    def post(self, request):
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

        serializer = WordExtractorAnalyzeSerializer(
            data={
                "text_input": request.data.get("text_input", ""),
                "selected_hsk_levels": raw_levels,
                "min_frequency": request.data.get("min_frequency", 2),
            }
        )
        serializer.is_valid(raise_exception=True)

        uploaded_files = []
        for uploaded in request.FILES.getlist("files"):
            uploaded_files.append((uploaded.name, uploaded.read()))

        try:
            payload = analyze_word_extractor(
                uploaded_files=uploaded_files,
                text_input=serializer.validated_data["text_input"],
                selected_hsk_levels=serializer.validated_data["selected_hsk_levels"],
                min_frequency=serializer.validated_data["min_frequency"],
            )
        except (ValueError, RuntimeError, ValidationError, InvalidFileError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(payload)
