from django.contrib import admin

from .models import PipelineResultRow, PipelineRun, PipelineRunEvent


@admin.register(PipelineRun)
class PipelineRunAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "profile_id", "total_input_words", "created_at")
    list_filter = ("status", "profile_id")
    search_fields = ("id", "profile_id")


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
