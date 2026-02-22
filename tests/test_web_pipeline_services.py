from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest
from django.contrib.auth import get_user_model

from pipeline_api.models import PipelineResultRow, PipelineRun, PipelineRunEvent, RunStatus
from pipeline_api.services import execute_pipeline_run


class _FakeTimestampTransformation:
    pass


@pytest.mark.django_db
def test_execute_pipeline_run_enriches_word_progress_when_transform_events_lack_it(tmp_path):
    user = get_user_model().objects.create_user(
        username="service-user",
        password="service-password",
    )
    run = PipelineRun.objects.create(
        owner=user,
        profile_id="lotm_zh_en_es",
        source_language="Chinese (Simplified)",
        selected_transform_names=["Timestamp"],
        ordered_transform_names=["Timestamp"],
        input_words=["你好", "谢谢", "苹果"],
        total_input_words=3,
        status=RunStatus.QUEUED,
    )

    prepared_run = SimpleNamespace(
        pipeline=SimpleNamespace(main_transformations=[object()], llm_transformations=[]),
        ordered_transform_names=["Timestamp"],
        selected_transforms=[_FakeTimestampTransformation()],
    )
    runtime = SimpleNamespace(
        pipeline_db_client=object(),
        all_transformations={"Timestamp": object()},
        transform_factory=lambda **_kwargs: {},
    )

    def _fake_execute_service(
        _self,
        *,
        prepared_run,
        words,
        llm_profile_id,
        progress_callback,
        dev_mode,
        execution_mode,
    ):
        del prepared_run, llm_profile_id, dev_mode
        assert execution_mode == "parallel_word_branches"
        progress_callback(
            {
                "event": "transform_start",
                "stage": "main",
                "transform_name": "FakeTimestampTransformation",
                "input_rows": len(words),
            }
        )
        progress_callback(
            {
                "event": "transform_complete",
                "stage": "main",
                "transform_name": "FakeTimestampTransformation",
                "duration_seconds": 0.42,
                "output_rows": len(words),
            }
        )
        return SimpleNamespace(
            df_results=pd.DataFrame(
                {
                    "word": words,
                    "translation": [f"T:{word}" for word in words],
                }
            ),
            saved_results_csv=Path(tmp_path) / "results.csv",
        )

    with (
        patch("pipeline_api.services.get_pipeline_runtime", return_value=runtime),
        patch(
            "pipeline_api.services.get_llm_profile",
            return_value=SimpleNamespace(source_language="Chinese (Simplified)"),
        ),
        patch(
            "pipeline_api.services.PipelineRunService.prepare_pipeline_run",
            return_value=prepared_run,
        ),
        patch(
            "pipeline_api.services.PipelineRunService.execute_pipeline_run",
            autospec=True,
            side_effect=_fake_execute_service,
        ),
    ):
        execute_pipeline_run(str(run.id))

    transform_start = PipelineRunEvent.objects.get(run=run, event_type="transform_start").payload
    transform_complete = PipelineRunEvent.objects.get(run=run, event_type="transform_complete").payload

    assert transform_start["current_word"] == "你好"
    assert transform_start["words_left"] == 2
    assert transform_complete["words_left"] == 0

    result_rows = list(PipelineResultRow.objects.filter(run=run).order_by("row_index"))
    assert len(result_rows) == 3
    assert all(str(row.row_data.get("timestamp", "")).strip() for row in result_rows)

    csv_df = pd.read_csv(Path(tmp_path) / "results.csv")
    assert "timestamp" in csv_df.columns
