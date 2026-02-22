import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ankineitor_web.settings")

app = Celery("ankineitor_web")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
