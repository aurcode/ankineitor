"""Tests for application-layer pipeline progress tracking."""

from ankineitor.application.pipeline_progress import PipelineProgressTracker


def test_pipeline_progress_tracker_updates_status_and_progress_from_events():
    tracker = PipelineProgressTracker(total_transform_steps=4)

    snapshot = tracker.consume_event({"event": "pipeline_start", "total_words": 12})
    assert snapshot.header_status == "info"
    assert snapshot.header_text == "Pipeline started."
    assert snapshot.status_text == "Preparing 12 words..."
    assert snapshot.progress_ratio == 0.02

    snapshot = tracker.consume_event(
        {"event": "cache_checked", "cached_words": 5, "new_words": 7}
    )
    assert snapshot.status_text == "Cache checked: 5 cached, 7 new words."
    assert snapshot.progress_ratio == 0.08

    snapshot = tracker.consume_event(
        {
            "event": "transform_complete",
            "stage": "main",
            "transform_name": "DummyTransform",
            "duration_seconds": 1.234,
        }
    )
    assert snapshot.status_text == "DummyTransform finished in 1.23s"
    assert snapshot.progress_ratio == 0.25
    assert snapshot.step_timings == [
        {"stage": "main", "step": "DummyTransform", "seconds": 1.23}
    ]

    snapshot = tracker.consume_event(
        {"event": "pipeline_complete", "total_duration_seconds": 9.876}
    )
    assert snapshot.header_status == "success"
    assert snapshot.header_text == "Pipeline complete."
    assert snapshot.status_text == "Total duration: 9.88s"
    assert snapshot.progress_ratio == 1.0


def test_pipeline_progress_tracker_returns_slowest_steps_descending():
    tracker = PipelineProgressTracker(total_transform_steps=5)
    tracker.consume_event(
        {
            "event": "transform_complete",
            "stage": "llm",
            "transform_name": "A",
            "duration_seconds": 0.5,
        }
    )
    tracker.consume_event(
        {
            "event": "transform_complete",
            "stage": "llm",
            "transform_name": "B",
            "duration_seconds": 2.0,
        }
    )
    tracker.consume_event(
        {
            "event": "transform_complete",
            "stage": "llm",
            "transform_name": "C",
            "duration_seconds": 1.0,
        }
    )

    assert tracker.slowest_steps(limit=2) == [
        {"stage": "llm", "step": "B", "seconds": 2.0},
        {"stage": "llm", "step": "C", "seconds": 1.0},
    ]
