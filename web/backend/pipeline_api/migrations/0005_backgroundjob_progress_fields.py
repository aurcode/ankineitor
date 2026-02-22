from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pipeline_api", "0004_backgroundjob_csv_and_canceled_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="backgroundjob",
            name="progress_ratio",
            field=models.FloatField(default=0.0),
        ),
        migrations.AddField(
            model_name="backgroundjob",
            name="status_text",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
