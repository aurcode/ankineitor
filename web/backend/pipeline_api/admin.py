from django.contrib import admin

from .models import (
    BackgroundJob,
    BackgroundJobEvent,
    FlashcardDataset,
    GeneratedAnkiDeck,
    PipelineResultRow,
    PipelineRun,
    PipelineRunEvent,
)


@admin.register(PipelineRun)
class PipelineRunAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "status", "profile_id", "total_input_words", "created_at")
    list_filter = ("status", "profile_id")
    search_fields = ("id", "profile_id", "owner__username")


@admin.register(PipelineRunEvent)
class PipelineRunEventAdmin(admin.ModelAdmin):
    list_display = ("id", "run", "sequence", "event_type", "stage", "transform_name", "created_at")
    list_filter = ("event_type", "stage")
    search_fields = ("run__id", "transform_name")


@admin.register(PipelineResultRow)
class PipelineResultRowAdmin(admin.ModelAdmin):
    list_display = ("id", "run", "row_index", "word", "created_at")
    list_filter = ("run",)
    search_fields = ("word", "run__id")


@admin.register(GeneratedAnkiDeck)
class GeneratedAnkiDeckAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "deck_name", "source_csv_name", "file_size_bytes", "created_at")
    search_fields = ("deck_name", "source_csv_name", "owner__username")


@admin.register(FlashcardDataset)
class FlashcardDatasetAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "source_type", "source_label", "total_cards", "created_at")
    list_filter = ("source_type",)
    search_fields = ("source_label", "owner__username")


@admin.register(BackgroundJob)
class BackgroundJobAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "job_type", "status", "created_at")
    list_filter = ("job_type", "status")
    search_fields = ("id", "owner__username")


@admin.register(BackgroundJobEvent)
class BackgroundJobEventAdmin(admin.ModelAdmin):
    list_display = ("id", "job", "sequence", "event_type", "created_at")
    list_filter = ("event_type",)
    search_fields = ("job__id", "job__owner__username")
