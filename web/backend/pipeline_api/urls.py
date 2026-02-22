from django.urls import re_path

from .views import (
    PipelineOptionsView,
    PipelineRunAddCategoryView,
    PipelineRunCreateView,
    PipelineRunDetailView,
    PipelineRunResultsCsvView,
    PipelineRunResultsView,
)

urlpatterns = [
    re_path(r"^pipeline/options/?$", PipelineOptionsView.as_view(), name="pipeline-options"),
    re_path(r"^pipeline/runs/?$", PipelineRunCreateView.as_view(), name="pipeline-run-create"),
    re_path(r"^pipeline/runs/(?P<run_id>[0-9a-fA-F-]+)/?$", PipelineRunDetailView.as_view(), name="pipeline-run-detail"),
    re_path(
        r"^pipeline/runs/(?P<run_id>[0-9a-fA-F-]+)/results/?$",
        PipelineRunResultsView.as_view(),
        name="pipeline-run-results",
    ),
    re_path(
        r"^pipeline/runs/(?P<run_id>[0-9a-fA-F-]+)/results/csv/?$",
        PipelineRunResultsCsvView.as_view(),
        name="pipeline-run-results-csv",
    ),
    re_path(
        r"^pipeline/runs/(?P<run_id>[0-9a-fA-F-]+)/add-category/?$",
        PipelineRunAddCategoryView.as_view(),
        name="pipeline-run-add-category",
    ),
]
