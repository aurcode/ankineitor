from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from pipeline_api.models import PipelineResultRow, PipelineRun, PipelineRunEvent, RunStatus


@pytest.mark.django_db
def test_auth_token_endpoint_returns_token():
    user = get_user_model().objects.create_user(
        username="login-user",
        password="login-password",
    )

    client = APIClient()
    response = client.post(
        "/api/auth/token",
        {"username": "login-user", "password": "login-password"},
        format="json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["user"]["id"] == user.id
    assert payload["user"]["username"] == "login-user"
    assert "token" in payload
    assert Token.objects.filter(user=user, key=payload["token"]).exists()


@pytest.mark.django_db
@patch("pipeline_api.views.run_pipeline_task.delay")
@patch("pipeline_api.views.resolve_ordered_transform_names")
def test_create_pipeline_run_enqueues_worker(mock_resolve, mock_delay, authenticated_api_client):
    mock_resolve.return_value = (
        ["LLM Audio (Sentences)"],
        ["Timestamp", "LLM (Meanings/Sentences)", "LLM Audio (Sentences)"],
        "Chinese (Simplified)",
    )
    mock_delay.return_value = SimpleNamespace(id="task-123")

    client, user, _token = authenticated_api_client
    response = client.post(
        "/api/pipeline/runs",
        {
            "profile_id": "lotm_zh_en_es",
            "transform_names": ["LLM Audio (Sentences)"],
            "words": ["你好", "谢谢"],
        },
        format="json",
    )

    assert response.status_code == 201
    payload = response.json()
    run = PipelineRun.objects.get(pk=payload["id"])

    assert run.owner == user
    assert run.status == RunStatus.QUEUED
    assert run.total_input_words == 2
    assert run.celery_task_id == "task-123"
    assert payload["ordered_transform_names"] == [
        "Timestamp",
        "LLM (Meanings/Sentences)",
        "LLM Audio (Sentences)",
    ]


@pytest.mark.django_db
def test_get_run_status_returns_event_count(authenticated_api_client):
    client, user, _token = authenticated_api_client
    run = PipelineRun.objects.create(
        owner=user,
        profile_id="lotm_zh_en_es",
        source_language="Chinese (Simplified)",
        selected_transform_names=["Audio"],
        ordered_transform_names=["Timestamp", "Audio"],
        input_words=["word"],
        total_input_words=1,
    )
    PipelineRunEvent.objects.create(
        run=run,
        sequence=1,
        event_type="pipeline_start",
        payload={"event": "pipeline_start", "total_words": 1},
    )

    response = client.get(f"/api/pipeline/runs/{run.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(run.id)
    assert payload["event_count"] == 1


@pytest.mark.django_db
def test_get_run_status_returns_404_for_other_user(authenticated_api_client):
    client, _user, _token = authenticated_api_client
    stranger = get_user_model().objects.create_user("stranger", password="pass123")
    run = PipelineRun.objects.create(
        owner=stranger,
        profile_id="lotm_zh_en_es",
        source_language="Chinese (Simplified)",
        selected_transform_names=["Audio"],
        ordered_transform_names=["Timestamp", "Audio"],
        input_words=["word"],
        total_input_words=1,
    )

    response = client.get(f"/api/pipeline/runs/{run.id}")
    assert response.status_code == 404


@pytest.mark.django_db
def test_get_run_results_returns_paginated_rows_and_csv_url(authenticated_api_client):
    client, user, _token = authenticated_api_client
    run = PipelineRun.objects.create(
        owner=user,
        profile_id="lotm_zh_en_es",
        source_language="Chinese (Simplified)",
        selected_transform_names=["Audio"],
        ordered_transform_names=["Timestamp", "Audio"],
        input_words=["你好", "谢谢"],
        total_input_words=2,
        status=RunStatus.SUCCESS,
        csv_output_path="output/pipeline_results_by_profile/lotm_zh_en_es/results.csv",
        csv_download_name="results.csv",
    )
    PipelineResultRow.objects.create(
        run=run,
        row_index=0,
        word="你好",
        row_data={"word": "你好", "translation": "hello"},
    )
    PipelineResultRow.objects.create(
        run=run,
        row_index=1,
        word="谢谢",
        row_data={"word": "谢谢", "translation": "thanks"},
    )

    response = client.get(f"/api/pipeline/runs/{run.id}/results", {"page": 1, "page_size": 1})

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == str(run.id)
    assert payload["count"] == 2
    assert payload["csv_url"].endswith(f"/api/pipeline/runs/{run.id}/results/csv")
    assert len(payload["results"]) == 1


@pytest.mark.django_db
@patch("pipeline_api.views.apply_category_to_run")
def test_add_category_endpoint_updates_results(mock_apply_category, authenticated_api_client):
    client, user, _token = authenticated_api_client
    run = PipelineRun.objects.create(
        owner=user,
        profile_id="lotm_zh_en_es",
        source_language="Chinese (Simplified)",
        selected_transform_names=["Audio"],
        ordered_transform_names=["Timestamp", "Audio"],
        input_words=["你好"],
        total_input_words=1,
        status=RunStatus.SUCCESS,
    )

    mock_apply_category.return_value = {"category": "HSK1", "updated_rows": 5}

    response = client.post(
        f"/api/pipeline/runs/{run.id}/add-category",
        {"category": "HSK1"},
        format="json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["category"] == "HSK1"
    assert payload["updated_rows"] == 5
    mock_apply_category.assert_called_once_with(str(run.id), "HSK1")
