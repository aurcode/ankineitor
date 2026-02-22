"""Application-level progress state tracking for pipeline runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PipelineProgressSnapshot:
    """Current pipeline progress view model (UI-framework agnostic)."""

    progress_ratio: float
    status_text: Optional[str] = None
    header_status: Optional[str] = None
    header_text: Optional[str] = None
    step_timings: List[Dict[str, Any]] = field(default_factory=list)


class PipelineProgressTracker:
    """Consumes pipeline events and maintains progress/status/timing state."""

    def __init__(self, total_transform_steps: int):
        self.total_transform_steps = max(1, int(total_transform_steps or 1))
        self.steps_completed = 0
        self._progress_ratio = 0.0
        self._status_text: Optional[str] = None
        self._header_status: Optional[str] = None
        self._header_text: Optional[str] = None
        self._step_timings: List[Dict[str, Any]] = []

    def consume_event(self, event: Dict[str, Any]) -> PipelineProgressSnapshot:
        event_type = str(event.get("event", ""))

        if event_type == "pipeline_start":
            total_words = int(event.get("total_words", 0) or 0)
            self._header_status = "info"
            self._header_text = "Pipeline started."
            self._status_text = f"Preparing {total_words} words..."
            self._progress_ratio = max(self._progress_ratio, 0.02)
            return self.snapshot()

        if event_type == "cache_checked":
            cached_words = int(event.get("cached_words", 0) or 0)
            new_words = int(event.get("new_words", 0) or 0)
            self._status_text = (
                f"Cache checked: {cached_words} cached, {new_words} new words."
            )
            self._progress_ratio = max(self._progress_ratio, 0.08)
            return self.snapshot()

        if event_type == "transform_start":
            stage = str(event.get("stage", "step")).upper()
            name = str(event.get("transform_name", "") or "")
            self._status_text = f"Running {stage}: {name}..."
            return self.snapshot()

        if event_type == "transform_complete":
            step_complete = bool(event.get("step_complete", True))
            if step_complete:
                self.steps_completed += 1
            duration_seconds = float(event.get("duration_seconds", 0.0) or 0.0)
            transform_name = str(event.get("transform_name", ""))
            current_word = str(event.get("current_word", "") or "").strip()
            if step_complete:
                total_duration = float(
                    event.get("transform_total_duration_seconds", duration_seconds) or 0.0
                )
                self._step_timings.append(
                    {
                        "stage": str(event.get("stage", "")),
                        "step": transform_name,
                        "seconds": round(total_duration, 2),
                    }
                )
                self._status_text = (
                    f"{transform_name} finished in {total_duration:.2f}s"
                )
                completion_ratio = self.steps_completed / float(self.total_transform_steps)
                self._progress_ratio = min(0.95, max(self._progress_ratio, completion_ratio))
            else:
                queued_count = int(event.get("queued_count", 0) or 0)
                if current_word:
                    self._status_text = (
                        f"{transform_name}: finished '{current_word}', {queued_count} words queued."
                    )
                else:
                    self._status_text = (
                        f"{transform_name}: word finished in {duration_seconds:.2f}s, "
                        f"{queued_count} words queued."
                    )
            return self.snapshot()

        if event_type == "pipeline_complete":
            total_duration = float(event.get("total_duration_seconds", 0.0) or 0.0)
            self._header_status = "success"
            self._header_text = "Pipeline complete."
            self._status_text = f"Total duration: {total_duration:.2f}s"
            self._progress_ratio = 1.0
            return self.snapshot()

        return self.snapshot()

    def snapshot(self) -> PipelineProgressSnapshot:
        return PipelineProgressSnapshot(
            progress_ratio=float(self._progress_ratio),
            status_text=self._status_text,
            header_status=self._header_status,
            header_text=self._header_text,
            step_timings=list(self._step_timings),
        )

    def slowest_steps(self, limit: int = 3) -> List[Dict[str, Any]]:
        capped_limit = max(0, int(limit))
        return sorted(
            self._step_timings,
            key=lambda row: float(row.get("seconds", 0.0) or 0.0),
            reverse=True,
        )[:capped_limit]
