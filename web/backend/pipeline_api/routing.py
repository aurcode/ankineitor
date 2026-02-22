from django.urls import re_path

from .consumers import PipelineRunConsumer

websocket_urlpatterns = [
    re_path(
        r"^ws/pipeline/runs/(?P<run_id>[0-9a-fA-F-]+)/?$",
        PipelineRunConsumer.as_asgi(),
    ),
]
