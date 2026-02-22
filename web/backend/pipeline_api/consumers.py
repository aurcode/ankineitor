from __future__ import annotations

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .models import PipelineRun, PipelineRunEvent
from .services import run_group_name, serialize_event


class PipelineRunConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.run_id = str(self.scope["url_route"]["kwargs"]["run_id"])
        run_exists = await self._run_exists(self.run_id)
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
    def _run_exists(self, run_id: str) -> bool:
        return PipelineRun.objects.filter(pk=run_id).exists()

    @database_sync_to_async
    def _event_history(self, run_id: str):
        events = PipelineRunEvent.objects.filter(run_id=run_id).order_by("sequence")
        return [serialize_event(event) for event in events]
