from django.urls import re_path

from .views import (
    AnkiDeckDownloadView,
    AnkiDeckGenerateView,
    AnkiPresetsView,
    AuthTokenView,
    BackgroundJobDetailView,
    BackgroundJobEventsView,
    FlashcardDatasetCardView,
    FlashcardDatasetFromSavedView,
    FlashcardDatasetSummaryView,
    FlashcardDatasetUploadView,
    FlashcardSavedFilesView,
    FlashcardSavedProfilesView,
    PipelineOptionsView,
    PipelineRunAddCategoryView,
    PipelineRunCreateView,
    PipelineRunDetailView,
    PipelineRunResultsCsvView,
    PipelineRunResultsView,
    WordExtractorAnalyzeView,
)

urlpatterns = [
    re_path(r"^auth/token/?$", AuthTokenView.as_view(), name="auth-token"),
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
    re_path(r"^anki/presets/?$", AnkiPresetsView.as_view(), name="anki-presets"),
    re_path(r"^anki/decks/generate/?$", AnkiDeckGenerateView.as_view(), name="anki-deck-generate"),
    re_path(
        r"^anki/decks/(?P<artifact_id>[0-9a-fA-F-]+)/download/?$",
        AnkiDeckDownloadView.as_view(),
        name="anki-deck-download",
    ),
    re_path(
        r"^flashcards/saved-profiles/?$",
        FlashcardSavedProfilesView.as_view(),
        name="flashcards-saved-profiles",
    ),
    re_path(
        r"^flashcards/saved-files/?$",
        FlashcardSavedFilesView.as_view(),
        name="flashcards-saved-files",
    ),
    re_path(
        r"^flashcards/datasets/from-saved/?$",
        FlashcardDatasetFromSavedView.as_view(),
        name="flashcards-dataset-from-saved",
    ),
    re_path(
        r"^flashcards/datasets/upload/?$",
        FlashcardDatasetUploadView.as_view(),
        name="flashcards-dataset-upload",
    ),
    re_path(
        r"^flashcards/datasets/(?P<dataset_id>[0-9a-fA-F-]+)/?$",
        FlashcardDatasetSummaryView.as_view(),
        name="flashcards-dataset-summary",
    ),
    re_path(
        r"^flashcards/datasets/(?P<dataset_id>[0-9a-fA-F-]+)/card/?$",
        FlashcardDatasetCardView.as_view(),
        name="flashcards-dataset-card",
    ),
    re_path(
        r"^word-extractor/analyze/?$",
        WordExtractorAnalyzeView.as_view(),
        name="word-extractor-analyze",
    ),
    re_path(
        r"^jobs/(?P<job_id>[0-9a-fA-F-]+)/?$",
        BackgroundJobDetailView.as_view(),
        name="background-job-detail",
    ),
    re_path(
        r"^jobs/(?P<job_id>[0-9a-fA-F-]+)/events/?$",
        BackgroundJobEventsView.as_view(),
        name="background-job-events",
    ),
]
