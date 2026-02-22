from django.db import migrations, models
import uuid


class Migration(migrations.Migration):
    dependencies = [
        ("pipeline_api", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="GeneratedAnkiDeck",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("deck_name", models.CharField(max_length=160)),
                ("source_csv_name", models.CharField(max_length=255)),
                ("output_path", models.TextField()),
                ("file_size_bytes", models.PositiveBigIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="FlashcardDataset",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "source_type",
                    models.CharField(
                        choices=[("saved", "Saved Pipeline CSV"), ("upload", "Uploaded CSV")],
                        max_length=12,
                    ),
                ),
                ("source_label", models.CharField(max_length=255)),
                ("csv_path", models.TextField()),
                ("total_cards", models.PositiveIntegerField(default=0)),
                ("columns", models.JSONField(default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
