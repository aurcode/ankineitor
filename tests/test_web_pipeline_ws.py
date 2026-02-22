from __future__ import annotations

import pytest
from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator

from ankineitor_web.asgi import application
from pipeline_api.models import PipelineRun
from pipeline_api.services import record_run_event


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_websocket_streams_history_and_live_events(settings):
    settings.CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }

    run = await sync_to_async(PipelineRun.objects.create)(
        profile_id="lotm_zh_en_es",
        source_language="Chinese (Simplified)",
        selected_transform_names=["Audio"],
        ordered_transform_names=["Timestamp", "Audio"],
        input_words=["你好"],
        total_input_words=1,
    )

    await sync_to_async(record_run_event)(str(run.id), {"event": "pipeline_start", "total_words": 1})

    communicator = WebsocketCommunicator(application, f"/ws/pipeline/runs/{run.id}")
    connected, _ = await communicator.connect()
    assert connected

    history_message = await communicator.receive_json_from()
    assert history_message["type"] == "pipeline_event"
    assert history_message["event"]["payload"]["event"] == "pipeline_start"
    assert history_message["event"]["sequence"] == 1

    await sync_to_async(record_run_event)(
        str(run.id),
        {
            "event": "transform_start",
            "stage": "main",
            "transform_name": "AudioTransformation",
        },
    )

    live_message = await communicator.receive_json_from()
    assert live_message["type"] == "pipeline_event"
    assert live_message["event"]["payload"]["event"] == "transform_start"
    assert live_message["event"]["sequence"] == 2

    await communicator.disconnect()
