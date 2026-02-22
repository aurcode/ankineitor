import uuid

from django.conf import settings
from django.db import models


class RunStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    RETRYING = "retrying", "Retrying"
    PAUSED = "paused", "Paused"
    CANCELED = "canceled", "Canceled"
    SUCCESS = "success", "Success"
    ERROR = "error", "Error"


class FlashcardDatasetSourceType(models.TextChoices):
    SAVED = "saved", "Saved Pipeline CSV"
    UPLOAD = "upload", "Uploaded CSV"


class PipelineRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pipeline_runs",
        null=True,
        blank=True,
    )
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


class GeneratedAnkiDeck(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="generated_anki_decks",
        null=True,
        blank=True,
    )
    deck_name = models.CharField(max_length=160)
    source_csv_name = models.CharField(max_length=255)
    output_path = models.TextField()
    file_size_bytes = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class FlashcardDataset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="flashcard_datasets",
        null=True,
        blank=True,
    )
    source_type = models.CharField(
        max_length=12,
        choices=FlashcardDatasetSourceType.choices,
    )
    source_label = models.CharField(max_length=255)
    csv_path = models.TextField()
    total_cards = models.PositiveIntegerField(default=0)
    columns = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class BackgroundJobType(models.TextChoices):
    ANKI_DECK = "anki_deck", "Anki Deck"
    WORD_EXTRACTOR = "word_extractor", "Word Extractor"


class BackgroundJobStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    SUCCESS = "success", "Success"
    ERROR = "error", "Error"
    CANCELED = "canceled", "Canceled"


class BackgroundJob(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="background_jobs",
    )
    job_type = models.CharField(max_length=32, choices=BackgroundJobType.choices)
    status = models.CharField(
        max_length=16,
        choices=BackgroundJobStatus.choices,
        default=BackgroundJobStatus.QUEUED,
    )
    progress_ratio = models.FloatField(default=0.0)
    status_text = models.CharField(max_length=255, blank=True)
    input_payload = models.JSONField(default=dict)
    result_payload = models.JSONField(default=dict)
    csv_output_path = models.TextField(blank=True)
    csv_download_name = models.CharField(max_length=256, blank=True)
    error_message = models.TextField(blank=True)
    celery_task_id = models.CharField(max_length=128, blank=True)
    last_event_sequence = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]


class BackgroundJobEvent(models.Model):
    job = models.ForeignKey(
        BackgroundJob,
        on_delete=models.CASCADE,
        related_name="events",
    )
    sequence = models.PositiveIntegerField()
    event_type = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sequence"]
        unique_together = ("job", "sequence")
