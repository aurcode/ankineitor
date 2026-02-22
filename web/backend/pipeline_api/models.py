import uuid

from django.db import models


class RunStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    RETRYING = "retrying", "Retrying"
    SUCCESS = "success", "Success"
    ERROR = "error", "Error"


class PipelineRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(
        max_length=16,
        choices=RunStatus.choices,
        default=RunStatus.QUEUED,
    )
    profile_id = models.CharField(max_length=128)
    source_language = models.CharField(max_length=128, blank=True)
    selected_transform_names = models.JSONField(default=list)
    ordered_transform_names = models.JSONField(default=list)
    input_words = models.JSONField(default=list)
    total_input_words = models.PositiveIntegerField(default=0)
    celery_task_id = models.CharField(max_length=128, blank=True)
    error_message = models.TextField(blank=True)
    csv_output_path = models.TextField(blank=True)
    csv_download_name = models.CharField(max_length=256, blank=True)
    total_duration_seconds = models.FloatField(null=True, blank=True)
    counters = models.JSONField(default=dict)
    slowest_steps = models.JSONField(default=list)
    last_event_sequence = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]


class PipelineRunEvent(models.Model):
    run = models.ForeignKey(
        PipelineRun,
        on_delete=models.CASCADE,
        related_name="events",
    )
    sequence = models.PositiveIntegerField()
    event_type = models.CharField(max_length=64)
    stage = models.CharField(max_length=32, blank=True)
    transform_name = models.CharField(max_length=128, blank=True)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sequence"]
        unique_together = ("run", "sequence")


class PipelineResultRow(models.Model):
    run = models.ForeignKey(
        PipelineRun,
        on_delete=models.CASCADE,
        related_name="results",
    )
    row_index = models.PositiveIntegerField()
    word = models.CharField(max_length=256, db_index=True)
    row_data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["row_index"]
        unique_together = ("run", "row_index")
