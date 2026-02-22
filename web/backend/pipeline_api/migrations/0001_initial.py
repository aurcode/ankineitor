from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="PipelineRun",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("queued", "Queued"),
                            ("running", "Running"),
                            ("retrying", "Retrying"),
                            ("success", "Success"),
                            ("error", "Error"),
                        ],
                        default="queued",
                        max_length=16,
                    ),
                ),
                ("profile_id", models.CharField(max_length=128)),
                ("source_language", models.CharField(blank=True, max_length=128)),
                ("selected_transform_names", models.JSONField(default=list)),
                ("ordered_transform_names", models.JSONField(default=list)),
                ("input_words", models.JSONField(default=list)),
                ("total_input_words", models.PositiveIntegerField(default=0)),
                ("celery_task_id", models.CharField(blank=True, max_length=128)),
                ("error_message", models.TextField(blank=True)),
                ("csv_output_path", models.TextField(blank=True)),
                ("csv_download_name", models.CharField(blank=True, max_length=256)),
                ("total_duration_seconds", models.FloatField(blank=True, null=True)),
                ("counters", models.JSONField(default=dict)),
                ("slowest_steps", models.JSONField(default=list)),
                ("last_event_sequence", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="PipelineRunEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sequence", models.PositiveIntegerField()),
                ("event_type", models.CharField(max_length=64)),
                ("stage", models.CharField(blank=True, max_length=32)),
                ("transform_name", models.CharField(blank=True, max_length=128)),
                ("payload", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="events",
                        to="pipeline_api.pipelinerun",
                    ),
                ),
            ],
            options={
                "ordering": ["sequence"],
                "unique_together": {("run", "sequence")},
            },
        ),
        migrations.CreateModel(
            name="PipelineResultRow",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("row_index", models.PositiveIntegerField()),
                ("word", models.CharField(db_index=True, max_length=256)),
                ("row_data", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="results",
                        to="pipeline_api.pipelinerun",
                    ),
                ),
            ],
            options={
                "ordering": ["row_index"],
                "unique_together": {("run", "row_index")},
            },
        ),
    ]
