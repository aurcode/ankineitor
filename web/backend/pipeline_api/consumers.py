from __future__ import annotations

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .models import BackgroundJob, BackgroundJobEvent, PipelineRun, PipelineRunEvent
from .services import run_group_name, serialize_event
from .tab_services import job_group_name, serialize_background_job, serialize_background_job_event


class PipelineRunConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return

        self.run_id = str(self.scope["url_route"]["kwargs"]["run_id"])
        run_exists = await self._run_exists_for_user(self.run_id, int(user.id))
        if not run_exists:
            await self.close(code=4404)
            return

        self.group_name = run_group_name(self.run_id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        history = await self._event_history(self.run_id)
        for event in history:
            await self.send_json({"type": "pipeline_event", "event": event})

    async def disconnect(self, close_code):
        del close_code
        group_name = getattr(self, "group_name", None)
        if group_name:
            await self.channel_layer.group_discard(group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        del content, kwargs

    async def pipeline_event(self, event):
        payload = dict(event.get("payload") or {})
        await self.send_json({"type": "pipeline_event", "event": payload})

    @database_sync_to_async
    def _run_exists_for_user(self, run_id: str, user_id: int) -> bool:
        return PipelineRun.objects.filter(pk=run_id, owner_id=user_id).exists()

    @database_sync_to_async
    def _event_history(self, run_id: str):
        events = PipelineRunEvent.objects.filter(run_id=run_id).order_by("sequence")
        return [serialize_event(event) for event in events]


class BackgroundJobConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return

        self.job_id = str(self.scope["url_route"]["kwargs"]["job_id"])
        job_exists = await self._job_exists_for_user(self.job_id, int(user.id))
        if not job_exists:
            await self.close(code=4404)
            return

        self.group_name = job_group_name(self.job_id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        snapshot = await self._job_snapshot(self.job_id)
        await self.send_json({"type": "job_snapshot", "job": snapshot})

        history = await self._event_history(self.job_id)
        for event in history:
            await self.send_json({"type": "job_event", "event": event})

    async def disconnect(self, close_code):
        del close_code
        group_name = getattr(self, "group_name", None)
        if group_name:
            await self.channel_layer.group_discard(group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        del content, kwargs

    async def background_job_event(self, event):
        payload = dict(event.get("payload") or {})
        await self.send_json({"type": "job_event", "event": payload})

    @database_sync_to_async
    def _job_exists_for_user(self, job_id: str, user_id: int) -> bool:
        return BackgroundJob.objects.filter(pk=job_id, owner_id=user_id).exists()

    @database_sync_to_async
    def _job_snapshot(self, job_id: str):
        job = BackgroundJob.objects.get(pk=job_id)
        return serialize_background_job(job)

    @database_sync_to_async
    def _event_history(self, job_id: str):
        events = BackgroundJobEvent.objects.filter(job_id=job_id).order_by("sequence")
        return [serialize_background_job_event(event) for event in events]
