from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
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
@patch("pipeline_api.views.run_pipeline_task.delay")
def test_rerun_pipeline_block_enqueues_new_run_with_same_words(
    mock_delay,
    authenticated_api_client,
):
    mock_delay.return_value = SimpleNamespace(id="task-rerun-123")

    client, user, _token = authenticated_api_client
    source_run = PipelineRun.objects.create(
        owner=user,
        profile_id="lotm_zh_en_es",
        source_language="Chinese (Simplified)",
        selected_transform_names=["LLM Audio (Sentences)"],
        ordered_transform_names=["Timestamp", "LLM (Meanings/Sentences)", "LLM Audio (Sentences)"],
        input_words=["你好", "谢谢"],
        total_input_words=2,
        status=RunStatus.SUCCESS,
    )

    response = client.post(
        f"/api/pipeline/runs/{source_run.id}/rerun-block",
        {"transform_name": "LLM Audio (Sentences)"},
        format="json",
    )

    assert response.status_code == 201
    payload = response.json()
    rerun = PipelineRun.objects.get(pk=payload["id"])
    assert rerun.id != source_run.id
    assert rerun.owner == user
    assert rerun.input_words == source_run.input_words
    assert rerun.total_input_words == source_run.total_input_words
    assert rerun.celery_task_id == "task-rerun-123"
    assert payload["ordered_transform_names"] == [
        "LLM (Meanings/Sentences)",
        "LLM Audio (Sentences)",
    ]
    assert payload["selected_transform_names"] == ["LLM Audio (Sentences)"]


@pytest.mark.django_db
def test_rerun_pipeline_block_rejects_unknown_transform_for_run(authenticated_api_client):
    client, user, _token = authenticated_api_client
    source_run = PipelineRun.objects.create(
        owner=user,
        profile_id="lotm_zh_en_es",
        source_language="Chinese (Simplified)",
        selected_transform_names=["Audio"],
        ordered_transform_names=["Timestamp", "Audio"],
        input_words=["你好"],
        total_input_words=1,
        status=RunStatus.SUCCESS,
    )

    response = client.post(
        f"/api/pipeline/runs/{source_run.id}/rerun-block",
        {"transform_name": "LLM Audio (Sentences)"},
        format="json",
    )

    assert response.status_code == 400
    assert "Unknown transform" in response.json()["detail"]


@pytest.mark.django_db
def test_list_pipeline_runs_returns_owner_scoped_history_with_filters(authenticated_api_client):
    client, user, _token = authenticated_api_client
    other_user = get_user_model().objects.create_user("other-history", password="pass123")

    first = PipelineRun.objects.create(
        owner=user,
        profile_id="lotm_zh_en_es",
        source_language="Chinese (Simplified)",
        selected_transform_names=["Audio"],
        ordered_transform_names=["Timestamp", "Audio"],
        input_words=["你好"],
        total_input_words=1,
        status=RunStatus.SUCCESS,
    )
    PipelineRunEvent.objects.create(
        run=first,
        sequence=1,
        event_type="pipeline_complete",
        payload={"event": "pipeline_complete"},
    )
    second = PipelineRun.objects.create(
        owner=user,
        profile_id="lotm_zh_en_es",
        source_language="Chinese (Simplified)",
        selected_transform_names=["Audio"],
        ordered_transform_names=["Timestamp", "Audio"],
        input_words=["谢谢"],
        total_input_words=1,
        status=RunStatus.RUNNING,
    )
    PipelineRun.objects.create(
        owner=other_user,
        profile_id="lotm_zh_en_es",
        source_language="Chinese (Simplified)",
        selected_transform_names=["Audio"],
        ordered_transform_names=["Timestamp", "Audio"],
        input_words=["陌生人"],
        total_input_words=1,
        status=RunStatus.SUCCESS,
    )

    response = client.get("/api/pipeline/runs", {"limit": 10})
    assert response.status_code == 200
    payload = response.json()
    returned_ids = [row["id"] for row in payload["runs"]]
    assert returned_ids == [str(second.id), str(first.id)]
    assert payload["runs"][1]["event_count"] == 1

    filtered_response = client.get("/api/pipeline/runs", {"status": "success", "limit": 10})
    assert filtered_response.status_code == 200
    filtered_payload = filtered_response.json()
    assert [row["id"] for row in filtered_payload["runs"]] == [str(first.id)]


@pytest.mark.django_db
def test_list_pipeline_runs_rejects_invalid_status(authenticated_api_client):
    client, _user, _token = authenticated_api_client
    response = client.get("/api/pipeline/runs", {"status": "bad-status"})
    assert response.status_code == 400
    assert "status must be one of" in response.json()["detail"]


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
    assert "translation" not in payload["columns"]
    assert "pinyin" not in payload["columns"]
    assert "timestamp" in payload["columns"]
    assert len(payload["results"]) == 1
    assert "translation" not in payload["results"][0]["row_data"]
    assert "pinyin" not in payload["results"][0]["row_data"]
    assert payload["results"][0]["row_data"].get("timestamp")


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


@pytest.mark.django_db
def test_generated_rows_list_and_detail_are_owner_scoped(authenticated_api_client):
    client, user, token = authenticated_api_client
    other_user = get_user_model().objects.create_user("other-generated", password="pass123")

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
    other_run = PipelineRun.objects.create(
        owner=other_user,
        profile_id="lotm_zh_en_es",
        source_language="Chinese (Simplified)",
        selected_transform_names=["Audio"],
        ordered_transform_names=["Timestamp", "Audio"],
        input_words=["陌生"],
        total_input_words=1,
        status=RunStatus.SUCCESS,
    )

    image_dir = Path("my_image_files")
    image_dir.mkdir(parents=True, exist_ok=True)
    image_path = image_dir / f"generated_row_{uuid4().hex}.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n")

    try:
        owned_row = PipelineResultRow.objects.create(
            run=run,
            row_index=0,
            word="你好",
            row_data={
                "word": "你好",
                "profile_id": "lotm_zh_en_es",
                "meaning_english": "hello",
                "picture": image_path.as_posix(),
            },
        )
        PipelineResultRow.objects.create(
            run=other_run,
            row_index=0,
            word="陌生",
            row_data={"word": "陌生", "meaning_english": "strange"},
        )

        response = client.get("/api/generated/rows", {"search": "你"})
        assert response.status_code == 200
        payload = response.json()
        assert payload["count"] == 1
        assert payload["results"][0]["row_id"] == owned_row.id
        assert payload["results"][0]["word"] == "你好"

        detail = client.get(f"/api/generated/rows/{owned_row.id}")
        assert detail.status_code == 200
        detail_payload = detail.json()["row"]
        assert detail_payload["row_id"] == owned_row.id
        assert detail_payload["run_id"] == str(run.id)
        assert detail_payload["word"] == "你好"
        assert detail_payload["card"]["front"]["word"] == "你好"
        assert detail_payload["card"]["back"]["image"]["picture"]
        assert "/api/flashcards/assets?" in detail_payload["card"]["back"]["image"]["picture"]
        assert token.key in detail_payload["card"]["back"]["image"]["picture"]
    finally:
        image_path.unlink(missing_ok=True)


@pytest.mark.django_db
def test_generated_row_update_persists_data(authenticated_api_client):
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
    row = PipelineResultRow.objects.create(
        run=run,
        row_index=0,
        word="你好",
        row_data={"word": "你好", "meaning_english": "old"},
    )

    response = client.post(
        f"/api/generated/rows/{row.id}/update",
        {"updates": {"meaning_english": "new meaning", "sentence_1": "新的句子"}},
        format="json",
    )
    assert response.status_code == 200
    payload = response.json()["row"]
    assert payload["row_data"]["meaning_english"] == "new meaning"
    assert payload["row_data"]["sentence_1"] == "新的句子"

    row.refresh_from_db()
    assert row.row_data["meaning_english"] == "new meaning"
    assert row.row_data["sentence_1"] == "新的句子"


@pytest.mark.django_db
@patch("pipeline_api.views.rerun_generated_row_process")
def test_generated_row_rerun_endpoint_calls_service(mock_rerun_generated_row_process, authenticated_api_client):
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
    row = PipelineResultRow.objects.create(
        run=run,
        row_index=0,
        word="你好",
        row_data={"word": "你好", "meaning_english": "old"},
    )
    mock_rerun_generated_row_process.return_value = {
        "row_id": row.id,
        "run_id": str(run.id),
        "run_status": "success",
        "profile_id": "lotm_zh_en_es",
        "row_index": 0,
        "word": "你好",
        "created_at": "2026-02-22T00:00:00+00:00",
        "row_data": {"word": "你好", "meaning_english": "new"},
        "card": {
            "index": 0,
            "total": 1,
            "front": {
                "word": "你好",
                "pronunciation": "",
                "part_of_speech": "",
                "register": "",
                "profile_id": "lotm_zh_en_es",
                "timestamp": "",
                "audio": "",
            },
            "back": {
                "meaning_english": "new",
                "meaning_spanish": "",
                "details": {},
                "relationships": {"synonyms": [], "antonyms": [], "collocations": []},
                "sentences": [],
                "image": {
                    "picture": "",
                    "image_term_type": "",
                    "visual_description": "",
                    "master_image_prompt": "",
                    "image_generation_skip_reason": "",
                    "image_render_status": "",
                    "image_render_skip_reason": "",
                },
            },
            "raw_row": {"word": "你好"},
        },
        "rerun_process": "meaning_sentences",
        "applied_transforms": ["LLM (Meanings/Sentences)"],
    }

    response = client.post(
        f"/api/generated/rows/{row.id}/rerun",
        {"process": "meaning_sentences"},
        format="json",
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["row"]["row_data"]["meaning_english"] == "new"
    assert payload["rerun_process"] == "meaning_sentences"
    mock_rerun_generated_row_process.assert_called_once_with(
        row_id=row.id,
        owner=user,
        process="meaning_sentences",
    )


@pytest.mark.django_db
@patch("pipeline_api.views.upload_generated_row_custom_image")
def test_generated_row_upload_image_endpoint_calls_service(
    mock_upload_generated_row_custom_image,
    authenticated_api_client,
):
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
    row = PipelineResultRow.objects.create(
        run=run,
        row_index=0,
        word="你好",
        row_data={"word": "你好", "meaning_english": "old"},
    )
    mock_upload_generated_row_custom_image.return_value = {
        "row_id": row.id,
        "run_id": str(run.id),
        "run_status": "success",
        "profile_id": "lotm_zh_en_es",
        "row_index": 0,
        "word": "你好",
        "created_at": "2026-02-22T00:00:00+00:00",
        "row_data": {
            "word": "你好",
            "picture": "media/generated_row_custom_images/test.png",
            "image_render_status": "custom_upload",
        },
        "card": {
            "index": 0,
            "total": 1,
            "front": {
                "word": "你好",
                "pronunciation": "",
                "part_of_speech": "",
                "register": "",
                "profile_id": "lotm_zh_en_es",
                "timestamp": "",
                "audio": "",
            },
            "back": {
                "meaning_english": "old",
                "meaning_spanish": "",
                "details": {},
                "relationships": {"synonyms": [], "antonyms": [], "collocations": []},
                "sentences": [],
                "image": {
                    "picture": "media/generated_row_custom_images/test.png",
                    "image_term_type": "",
                    "visual_description": "",
                    "master_image_prompt": "",
                    "image_generation_skip_reason": "",
                    "image_render_status": "custom_upload",
                    "image_render_skip_reason": "",
                },
            },
            "raw_row": {"word": "你好"},
        },
    }

    response = client.post(
        f"/api/generated/rows/{row.id}/upload-image",
        {
            "image_file": SimpleUploadedFile(
                "custom.png",
                b"\x89PNG\r\n\x1a\n",
                content_type="image/png",
            )
        },
        format="multipart",
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["row"]["card"]["back"]["image"]["picture"]
    mock_upload_generated_row_custom_image.assert_called_once()
