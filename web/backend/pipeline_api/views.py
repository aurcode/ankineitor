from __future__ import annotations

from pathlib import Path

from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse
from rest_framework import pagination, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PipelineResultRow, PipelineRun
from .serializers import (
    AddCategorySerializer,
    PipelineResultRowSerializer,
    PipelineRunCreateSerializer,
    PipelineRunSummarySerializer,
)
from .services import apply_category_to_run, build_pipeline_options, resolve_ordered_transform_names
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
