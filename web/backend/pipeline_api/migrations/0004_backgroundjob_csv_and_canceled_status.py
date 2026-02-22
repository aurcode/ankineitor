from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pipeline_api", "0003_owner_and_background_jobs"),
    ]

    operations = [
        migrations.AddField(
            model_name="backgroundjob",
            name="csv_download_name",
            field=models.CharField(blank=True, max_length=256),
        ),
        migrations.AddField(
            model_name="backgroundjob",
            name="csv_output_path",
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name="backgroundjob",
            name="status",
            field=models.CharField(
                choices=[
                    ("queued", "Queued"),
                    ("running", "Running"),
                    ("success", "Success"),
                    ("error", "Error"),
                    ("canceled", "Canceled"),
                ],
                default="queued",
                max_length=16,
            ),
        ),
    ]
