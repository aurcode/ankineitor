from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

from pipeline_api.models import (
    BackgroundJob,
    BackgroundJobEvent,
    BackgroundJobStatus,
    BackgroundJobType,
)


@pytest.mark.django_db
@patch("pipeline_api.views.get_anki_presets")
def test_get_anki_presets(mock_get_anki_presets, authenticated_api_client):
    mock_get_anki_presets.return_value = {
        "default": {"model_name": "Default"},
        "chinese_pipeline": {"model_name": "Chinese"},
    }

    client, _user, _token = authenticated_api_client
    response = client.get("/api/anki/presets")

    assert response.status_code == 200
    payload = response.json()
    assert payload["default"]["model_name"] == "Default"
    assert payload["chinese_pipeline"]["model_name"] == "Chinese"


@pytest.mark.django_db
@patch("pipeline_api.views.run_anki_background_job_task.delay")
@patch("pipeline_api.views.create_anki_background_job")
def test_generate_anki_deck_enqueues_background_job(mock_create_job, mock_delay, authenticated_api_client):
    client, user, _token = authenticated_api_client
    job = BackgroundJob.objects.create(
        owner=user,
        job_type=BackgroundJobType.ANKI_DECK,
        status=BackgroundJobStatus.QUEUED,
        input_payload={},
    )
    mock_create_job.return_value = job
    mock_delay.return_value = SimpleNamespace(id="anki-task-123")

    upload = SimpleUploadedFile(
        "cards.csv",
        b"word,translation\nhello,hola\n",
        content_type="text/csv",
    )

    response = client.post(
        "/api/anki/decks/generate",
        {
            "csv_file": upload,
            "deck_name": "My Deck",
            "config": '{"model_id":1,"model_name":"M","deck_id":2,"note_type":"N",'
            '"model_fields":[{"name":"Front"}],"model_builder":[{"csv_column":"word"}],'
            '"media_fields":[],"model_templates_yaml":{"main":[],"css":""},"tag_rules_yaml":[]}',
        },
        format="multipart",
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["job"]["id"] == str(job.id)
    assert payload["job"]["status"] == "queued"
    assert payload["job"]["progress_ratio"] == 0.0
    mock_create_job.assert_called_once()
    mock_delay.assert_called_once_with(str(job.id))
    job.refresh_from_db()
    assert job.celery_task_id == "anki-task-123"


@pytest.mark.django_db
def test_background_job_detail_is_owner_scoped(authenticated_api_client):
    client, _user, _token = authenticated_api_client
    other_user = get_user_model().objects.create_user("other", password="pass123")
    job = BackgroundJob.objects.create(
        owner=other_user,
        job_type=BackgroundJobType.ANKI_DECK,
        status=BackgroundJobStatus.QUEUED,
        input_payload={},
    )

    response = client.get(f"/api/jobs/{job.id}")
    assert response.status_code == 404


@pytest.mark.django_db
def test_background_job_events_endpoint(authenticated_api_client):
    client, user, _token = authenticated_api_client
    job = BackgroundJob.objects.create(
        owner=user,
        job_type=BackgroundJobType.WORD_EXTRACTOR,
        status=BackgroundJobStatus.RUNNING,
        input_payload={},
    )
    event = BackgroundJobEvent.objects.create(
        job=job,
        sequence=1,
        event_type="job_start",
        payload={"event": "job_start"},
    )

    response = client.get(f"/api/jobs/{job.id}/events")
    assert response.status_code == 200
    payload = response.json()
    assert payload["job_id"] == str(job.id)
    assert len(payload["events"]) == 1
    assert payload["events"][0]["sequence"] == event.sequence
    assert payload["events"][0]["payload"]["event"] == "job_start"


@pytest.mark.django_db
def test_background_job_list_filters_owner_and_type(authenticated_api_client):
    client, user, _token = authenticated_api_client
    other_user = get_user_model().objects.create_user("other-list", password="pass123")

    own_anki = BackgroundJob.objects.create(
        owner=user,
        job_type=BackgroundJobType.ANKI_DECK,
        status=BackgroundJobStatus.QUEUED,
        input_payload={},
    )
    BackgroundJob.objects.create(
        owner=user,
        job_type=BackgroundJobType.WORD_EXTRACTOR,
        status=BackgroundJobStatus.QUEUED,
        input_payload={},
    )
    BackgroundJob.objects.create(
        owner=other_user,
        job_type=BackgroundJobType.ANKI_DECK,
        status=BackgroundJobStatus.QUEUED,
        input_payload={},
    )

    response = client.get("/api/jobs", {"job_type": "anki_deck", "limit": 10})
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["jobs"]) == 1
    assert payload["jobs"][0]["id"] == str(own_anki.id)
    assert payload["jobs"][0]["job_type"] == "anki_deck"


@pytest.mark.django_db
@patch("pipeline_api.views.current_app.control.revoke")
def test_background_job_cancel_endpoint(mock_revoke, authenticated_api_client):
    client, user, _token = authenticated_api_client
    job = BackgroundJob.objects.create(
        owner=user,
        job_type=BackgroundJobType.WORD_EXTRACTOR,
        status=BackgroundJobStatus.RUNNING,
        input_payload={},
        celery_task_id="task-123",
    )

    response = client.post(f"/api/jobs/{job.id}/cancel", {}, format="json")
    assert response.status_code == 200
    payload = response.json()
    assert payload["job"]["status"] == "canceled"
    assert payload["job"]["status_text"] == "Canceled by user."
    job.refresh_from_db()
    assert job.status == BackgroundJobStatus.CANCELED
    mock_revoke.assert_called_once_with("task-123", terminate=False)


@pytest.mark.django_db
@patch("pipeline_api.views.run_anki_background_job_task.delay")
def test_background_job_retry_endpoint_enqueues_new_task(mock_delay, authenticated_api_client):
    client, user, _token = authenticated_api_client
    original = BackgroundJob.objects.create(
        owner=user,
        job_type=BackgroundJobType.ANKI_DECK,
        status=BackgroundJobStatus.ERROR,
        input_payload={"deck_name": "Retry Deck"},
    )
    mock_delay.return_value = SimpleNamespace(id="retry-task-123")

    response = client.post(f"/api/jobs/{original.id}/retry", {}, format="json")
    assert response.status_code == 202
    payload = response.json()

    new_job_id = payload["job"]["id"]
    assert new_job_id != str(original.id)
    new_job = BackgroundJob.objects.get(pk=new_job_id)
    assert new_job.owner == user
    assert new_job.job_type == BackgroundJobType.ANKI_DECK
    assert new_job.status == BackgroundJobStatus.QUEUED
    assert new_job.input_payload["deck_name"] == "Retry Deck"
    assert new_job.celery_task_id == "retry-task-123"
    mock_delay.assert_called_once_with(str(new_job.id))


@pytest.mark.django_db
def test_background_job_results_csv_download(authenticated_api_client):
    client, user, _token = authenticated_api_client
    output_dir = Path("tests") / "_tmp_artifacts"
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "test_word_extractor_job.csv"
    csv_path.write_text("word,frequency\n你好,3\n", encoding="utf-8")

    job = BackgroundJob.objects.create(
        owner=user,
        job_type=BackgroundJobType.WORD_EXTRACTOR,
        status=BackgroundJobStatus.SUCCESS,
        input_payload={},
        csv_output_path=csv_path.as_posix(),
        csv_download_name="words.csv",
    )

    response = client.get(f"/api/jobs/{job.id}/results/csv")
    assert response.status_code == 200
    assert "text/csv" in str(response.headers.get("Content-Type", ""))
    csv_path.unlink(missing_ok=True)


@pytest.mark.django_db
def test_flashcards_saved_files_requires_profile_id(authenticated_api_client):
    client, _user, _token = authenticated_api_client
    response = client.get("/api/flashcards/saved-files")

    assert response.status_code == 400
    assert "profile_id" in response.json()["detail"]


@pytest.mark.django_db
@patch("pipeline_api.views.create_flashcard_dataset_from_saved")
def test_flashcards_dataset_from_saved_passes_owner(mock_create, authenticated_api_client):
    client, user, _token = authenticated_api_client
    mock_create.return_value = {
        "dataset_id": str(uuid4()),
        "source_type": "saved",
        "source_label": "profile:file.csv",
        "total_cards": 10,
        "columns": ["word"],
        "available_profiles": ["lotm_zh_en_es"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    response = client.post(
        "/api/flashcards/datasets/from-saved",
        {"profile_id": "lotm_zh_en_es", "file_name": "file.csv"},
        format="json",
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["source_type"] == "saved"
    assert payload["total_cards"] == 10
    mock_create.assert_called_once_with(
        owner=user,
        profile_id="lotm_zh_en_es",
        file_name="file.csv",
    )


@pytest.mark.django_db
@patch("pipeline_api.views.run_word_extractor_background_job_task.delay")
@patch("pipeline_api.views.create_word_extractor_background_job")
def test_word_extractor_analyze_enqueues_background_job(
    mock_create_job,
    mock_delay,
    authenticated_api_client,
):
    client, user, _token = authenticated_api_client
    job = BackgroundJob.objects.create(
        owner=user,
        job_type=BackgroundJobType.WORD_EXTRACTOR,
        status=BackgroundJobStatus.QUEUED,
        input_payload={},
    )
    mock_create_job.return_value = job
    mock_delay.return_value = SimpleNamespace(id="extract-task-123")

    response = client.post(
        "/api/word-extractor/analyze",
        {
            "text_input": "你好你好你好",
            "selected_hsk_levels": ["hsk1"],
            "min_frequency": 2,
        },
        format="multipart",
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["job"]["id"] == str(job.id)
    assert payload["job"]["job_type"] == "word_extractor"
    assert payload["job"]["progress_ratio"] == 0.0
    mock_create_job.assert_called_once()
    mock_delay.assert_called_once_with(str(job.id))
