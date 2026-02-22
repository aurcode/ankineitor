from __future__ import annotations

import pytest
from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token

from ankineitor_web.asgi import application
from pipeline_api.models import BackgroundJob, BackgroundJobType, PipelineRun
from pipeline_api.services import record_run_event
from pipeline_api.tab_services import record_background_job_event


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_websocket_streams_history_and_live_events(settings):
    settings.CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }

    user = await sync_to_async(get_user_model().objects.create_user)(
        username="ws-user",
        password="ws-password",
    )
    token = await sync_to_async(Token.objects.create)(user=user)

    run = await sync_to_async(PipelineRun.objects.create)(
        owner=user,
        profile_id="lotm_zh_en_es",
        source_language="Chinese (Simplified)",
        selected_transform_names=["Audio"],
        ordered_transform_names=["Timestamp", "Audio"],
        input_words=["你好"],
        total_input_words=1,
    )

    await sync_to_async(record_run_event)(str(run.id), {"event": "pipeline_start", "total_words": 1})

    communicator = WebsocketCommunicator(
        application,
        f"/ws/pipeline/runs/{run.id}?token={token.key}",
    )
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


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_websocket_rejects_run_for_wrong_user(settings):
    settings.CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }

    owner = await sync_to_async(get_user_model().objects.create_user)(
        username="owner",
        password="owner-pass",
    )
    other_user = await sync_to_async(get_user_model().objects.create_user)(
        username="other",
        password="other-pass",
    )
    other_token = await sync_to_async(Token.objects.create)(user=other_user)

    run = await sync_to_async(PipelineRun.objects.create)(
        owner=owner,
        profile_id="lotm_zh_en_es",
        source_language="Chinese (Simplified)",
        selected_transform_names=["Audio"],
        ordered_transform_names=["Timestamp", "Audio"],
        input_words=["你好"],
        total_input_words=1,
    )

    communicator = WebsocketCommunicator(
        application,
        f"/ws/pipeline/runs/{run.id}?token={other_token.key}",
    )
    connected, code = await communicator.connect()
    assert not connected
    assert code == 4404


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_background_job_websocket_streams_history_and_live_events(settings):
    settings.CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }

    user = await sync_to_async(get_user_model().objects.create_user)(
        username="job-user",
        password="job-password",
    )
    token = await sync_to_async(Token.objects.create)(user=user)

    job = await sync_to_async(BackgroundJob.objects.create)(
        owner=user,
        job_type=BackgroundJobType.WORD_EXTRACTOR,
        input_payload={},
    )
    await sync_to_async(record_background_job_event)(
        str(job.id),
        {"event": "job_queued", "job_type": job.job_type},
    )

    communicator = WebsocketCommunicator(
        application,
        f"/ws/jobs/{job.id}?token={token.key}",
    )
    connected, _ = await communicator.connect()
    assert connected

    snapshot_message = await communicator.receive_json_from()
    assert snapshot_message["type"] == "job_snapshot"
    assert snapshot_message["job"]["id"] == str(job.id)

    history_message = await communicator.receive_json_from()
    assert history_message["type"] == "job_event"
    assert history_message["event"]["payload"]["event"] == "job_queued"
    assert history_message["event"]["sequence"] == 1

    await sync_to_async(record_background_job_event)(
        str(job.id),
        {"event": "job_start", "job_type": job.job_type},
    )

    live_message = await communicator.receive_json_from()
    assert live_message["type"] == "job_event"
    assert live_message["event"]["payload"]["event"] == "job_start"
    assert live_message["event"]["sequence"] == 2

    await communicator.disconnect()
