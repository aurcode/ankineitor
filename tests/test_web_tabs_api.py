from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from pipeline_api.models import (
    BackgroundJob,
    BackgroundJobEvent,
    BackgroundJobStatus,
    BackgroundJobType,
    FlashcardDataset,
    FlashcardDatasetSourceType,
    PipelineRun,
    PipelineRunEvent,
    RunStatus,
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
@patch("pipeline_api.views.current_app.control.inspect")
def test_admin_monitor_requires_staff_user(mock_inspect, authenticated_api_client):
    client, _user, _token = authenticated_api_client

    response = client.get("/api/admin/monitor")

    assert response.status_code == 403
    assert "Admin access required" in response.json()["detail"]
    mock_inspect.assert_not_called()


@pytest.mark.django_db
@patch("pipeline_api.views.current_app.control.inspect")
def test_admin_monitor_returns_active_runs_jobs_and_worker_tasks(
    mock_inspect, authenticated_api_client
):
    _client, _user, _token = authenticated_api_client
    admin_user = get_user_model().objects.create_user(
        username="admin-monitor",
        password="pass123",
        is_staff=True,
    )
    admin_token = Token.objects.create(user=admin_user)
    admin_client = APIClient()
    admin_client.credentials(HTTP_AUTHORIZATION=f"Token {admin_token.key}")

    owner = get_user_model().objects.create_user("run-owner", password="pass123")
    run = PipelineRun.objects.create(
        owner=owner,
        profile_id="lotm_zh_en_es",
        source_language="Chinese (Simplified)",
        selected_transform_names=["Audio"],
        ordered_transform_names=["Timestamp", "Audio"],
        input_words=["你好", "谢谢"],
        total_input_words=2,
        status=RunStatus.RUNNING,
        celery_task_id="pipeline-task-123",
    )
    PipelineRunEvent.objects.create(
        run=run,
        sequence=1,
        event_type="transform_start",
        payload={
            "event": "transform_start",
            "transform_name": "Audio",
            "current_word": "你好",
            "words_left": 1,
            "running_count": 1,
            "queued_count": 1,
        },
    )

    job = BackgroundJob.objects.create(
        owner=owner,
        job_type=BackgroundJobType.ANKI_DECK,
        status=BackgroundJobStatus.RUNNING,
        progress_ratio=0.5,
        status_text="Generating deck...",
        input_payload={},
        celery_task_id="anki-task-456",
    )

    inspector = mock_inspect.return_value
    inspector.active.return_value = {
        "worker@1": [
            {
                "id": "pipeline-task-123",
                "name": "pipeline_api.tasks.run_pipeline_task",
                "args": "['run-id']",
                "kwargs": "{}",
            }
        ]
    }
    inspector.reserved.return_value = {
        "worker@1": [
            {
                "id": "anki-task-456",
                "name": "pipeline_api.tasks.run_anki_background_job_task",
                "args": "['job-id']",
                "kwargs": "{}",
            }
        ]
    }
    inspector.scheduled.return_value = {
        "worker@1": [
            {
                "eta": "2026-02-22T16:00:00+00:00",
                "request": {
                    "id": "scheduled-1",
                    "name": "pipeline_api.tasks.run_word_extractor_background_job_task",
                    "args": "['scheduled-job']",
                    "kwargs": "{}",
                },
            }
        ]
    }
    inspector.active_queues.return_value = {
        "worker@1": [{"name": "celery", "routing_key": "celery"}]
    }
    inspector.stats.return_value = {"worker@1": {"pool": {"max-concurrency": 4}}}

    response = admin_client.get("/api/admin/monitor")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["active_pipeline_runs"] == 1
    assert payload["summary"]["active_background_jobs"] == 1
    assert payload["summary"]["celery_workers"] == 1
    assert payload["summary"]["celery_active_tasks"] == 1
    assert payload["summary"]["celery_reserved_tasks"] == 1
    assert payload["summary"]["celery_scheduled_tasks"] == 1

    run_payload = payload["pipeline_runs"][0]
    assert run_payload["id"] == str(run.id)
    assert run_payload["owner_username"] == "run-owner"
    assert run_payload["current_transform"] == "Audio"
    assert run_payload["current_word"] == "你好"
    assert run_payload["words_left"] == 1
    assert run_payload["running_count"] == 1
    assert run_payload["queued_count"] == 1

    job_payload = payload["background_jobs"][0]
    assert job_payload["id"] == str(job.id)
    assert job_payload["owner_username"] == "run-owner"
    assert job_payload["progress_ratio"] == 0.5
    assert job_payload["status_text"] == "Generating deck..."

    celery_payload = payload["celery"]
    assert celery_payload["totals"]["workers"] == 1
    worker_payload = celery_payload["workers"][0]
    assert worker_payload["worker_name"] == "worker@1"
    assert worker_payload["queues"] == ["celery"]
    assert worker_payload["active_count"] == 1
    assert worker_payload["reserved_count"] == 1
    assert worker_payload["scheduled_count"] == 1


@pytest.mark.django_db
@patch("pipeline_api.views.current_app.control.revoke")
def test_admin_can_pause_pipeline_run(mock_revoke, authenticated_api_client):
    _client, _user, _token = authenticated_api_client
    admin_user = get_user_model().objects.create_user(
        username="admin-pause",
        password="pass123",
        is_staff=True,
    )
    admin_token = Token.objects.create(user=admin_user)
    admin_client = APIClient()
    admin_client.credentials(HTTP_AUTHORIZATION=f"Token {admin_token.key}")

    owner = get_user_model().objects.create_user("owner-pause", password="pass123")
    run = PipelineRun.objects.create(
        owner=owner,
        profile_id="lotm_zh_en_es",
        source_language="Chinese (Simplified)",
        selected_transform_names=["Audio"],
        ordered_transform_names=["Timestamp", "Audio"],
        input_words=["你好"],
        total_input_words=1,
        status=RunStatus.RUNNING,
        celery_task_id="pause-task-1",
    )

    response = admin_client.post(f"/api/admin/pipeline/runs/{run.id}/pause", {}, format="json")
    assert response.status_code == 200
    run.refresh_from_db()
    assert run.status == RunStatus.PAUSED
    assert "Paused by admin" in run.error_message
    mock_revoke.assert_called_once_with("pause-task-1", terminate=False)


@pytest.mark.django_db
@patch("pipeline_api.views.current_app.control.revoke")
def test_admin_can_cancel_pipeline_run(mock_revoke, authenticated_api_client):
    _client, _user, _token = authenticated_api_client
    admin_user = get_user_model().objects.create_user(
        username="admin-cancel",
        password="pass123",
        is_staff=True,
    )
    admin_token = Token.objects.create(user=admin_user)
    admin_client = APIClient()
    admin_client.credentials(HTTP_AUTHORIZATION=f"Token {admin_token.key}")

    owner = get_user_model().objects.create_user("owner-cancel", password="pass123")
    run = PipelineRun.objects.create(
        owner=owner,
        profile_id="lotm_zh_en_es",
        source_language="Chinese (Simplified)",
        selected_transform_names=["Audio"],
        ordered_transform_names=["Timestamp", "Audio"],
        input_words=["你好"],
        total_input_words=1,
        status=RunStatus.RETRYING,
        celery_task_id="cancel-task-1",
    )

    response = admin_client.post(f"/api/admin/pipeline/runs/{run.id}/cancel", {}, format="json")
    assert response.status_code == 200
    run.refresh_from_db()
    assert run.status == RunStatus.CANCELED
    assert "Canceled by admin" in run.error_message
    mock_revoke.assert_called_once_with("cancel-task-1", terminate=False)


@pytest.mark.django_db
@patch("pipeline_api.views.run_pipeline_task.delay")
def test_admin_can_resume_paused_pipeline_run(mock_delay, authenticated_api_client):
    _client, _user, _token = authenticated_api_client
    admin_user = get_user_model().objects.create_user(
        username="admin-resume",
        password="pass123",
        is_staff=True,
    )
    admin_token = Token.objects.create(user=admin_user)
    admin_client = APIClient()
    admin_client.credentials(HTTP_AUTHORIZATION=f"Token {admin_token.key}")

    owner = get_user_model().objects.create_user("owner-resume", password="pass123")
    run = PipelineRun.objects.create(
        owner=owner,
        profile_id="lotm_zh_en_es",
        source_language="Chinese (Simplified)",
        selected_transform_names=["Audio"],
        ordered_transform_names=["Timestamp", "Audio"],
        input_words=["你好"],
        total_input_words=1,
        status=RunStatus.PAUSED,
        celery_task_id="old-task",
        error_message="Paused by admin.",
    )
    mock_delay.return_value = SimpleNamespace(id="new-task-1")

    response = admin_client.post(f"/api/admin/pipeline/runs/{run.id}/resume", {}, format="json")
    assert response.status_code == 200
    run.refresh_from_db()
    assert run.status == RunStatus.QUEUED
    assert run.celery_task_id == "new-task-1"
    assert run.error_message == ""
    mock_delay.assert_called_once_with(str(run.id))


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
def test_flashcard_card_returns_asset_url_and_asset_endpoint_serves_file(authenticated_api_client):
    client, user, token = authenticated_api_client
    image_dir = Path("my_image_files")
    image_dir.mkdir(parents=True, exist_ok=True)
    image_path = image_dir / f"reviewer_asset_{uuid4().hex}.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    dataset_csv = Path("tests") / "_tmp_artifacts" / f"reviewer_cards_{uuid4().hex}.csv"
    dataset_csv.parent.mkdir(parents=True, exist_ok=True)
    dataset_csv.write_text(
        f"word,picture\nhello,{image_path.as_posix()}\n",
        encoding="utf-8",
    )

    try:
        dataset = FlashcardDataset.objects.create(
            owner=user,
            source_type=FlashcardDatasetSourceType.SAVED,
            source_label="test:reviewer",
            csv_path=dataset_csv.as_posix(),
            total_cards=1,
            columns=["word", "picture"],
        )

        card_response = client.get(
            f"/api/flashcards/datasets/{dataset.id}/card",
            {"index": 0},
        )
        assert card_response.status_code == 200
        picture_url = card_response.json()["back"]["image"]["picture"]
        assert picture_url.startswith("/api/flashcards/assets?")
        assert "/api/flashcards/assets?" in picture_url
        assert "token=" in picture_url

        parsed = urlparse(picture_url)
        relative_url = parsed.path
        if parsed.query:
            relative_url = f"{relative_url}?{parsed.query}"

        anonymous_client = APIClient()
        asset_response = anonymous_client.get(relative_url)
        assert asset_response.status_code == 200
        assert "image/png" in str(asset_response.headers.get("Content-Type", ""))
        assert token.key in picture_url
    finally:
        dataset_csv.unlink(missing_ok=True)
        image_path.unlink(missing_ok=True)


@pytest.mark.django_db
def test_flashcard_asset_rejects_paths_outside_allowed_directories(authenticated_api_client):
    _client, _user, token = authenticated_api_client
    anonymous_client = APIClient()
    response = anonymous_client.get(
        "/api/flashcards/assets",
        {"path": "../../etc/passwd", "token": token.key},
    )

    assert response.status_code == 403
    assert "outside allowed directories" in response.json()["detail"]


@pytest.mark.django_db
def test_flashcard_card_update_endpoint_persists_changes(authenticated_api_client):
    client, user, _token = authenticated_api_client
    dataset_csv = Path("tests") / "_tmp_artifacts" / f"reviewer_edit_{uuid4().hex}.csv"
    dataset_csv.parent.mkdir(parents=True, exist_ok=True)
    dataset_csv.write_text(
        "word,meaning_english,meaning_spanish\nhello,old,antiguo\n",
        encoding="utf-8",
    )

    try:
        dataset = FlashcardDataset.objects.create(
            owner=user,
            source_type=FlashcardDatasetSourceType.UPLOAD,
            source_label="edit-test",
            csv_path=dataset_csv.as_posix(),
            total_cards=1,
            columns=["word", "meaning_english", "meaning_spanish"],
        )

        response = client.post(
            f"/api/flashcards/datasets/{dataset.id}/card/update",
            {
                "index": 0,
                "updates": {
                    "meaning_english": "new meaning",
                    "meaning_spanish": "nuevo significado",
                },
            },
            format="json",
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["dataset"]["dataset_id"] == str(dataset.id)
        assert payload["card"]["back"]["meaning_english"] == "new meaning"
        assert payload["card"]["back"]["meaning_spanish"] == "nuevo significado"
        assert "new meaning" in dataset_csv.read_text(encoding="utf-8")
    finally:
        dataset_csv.unlink(missing_ok=True)


@pytest.mark.django_db
@patch("pipeline_api.views.rerun_flashcard_card_generation")
def test_flashcard_card_rerun_endpoint_calls_service(mock_rerun, authenticated_api_client):
    client, user, _token = authenticated_api_client
    dataset_csv = Path("tests") / "_tmp_artifacts" / f"reviewer_rerun_{uuid4().hex}.csv"
    dataset_csv.parent.mkdir(parents=True, exist_ok=True)
    dataset_csv.write_text("word\nhello\n", encoding="utf-8")

    try:
        dataset = FlashcardDataset.objects.create(
            owner=user,
            source_type=FlashcardDatasetSourceType.UPLOAD,
            source_label="rerun-test",
            csv_path=dataset_csv.as_posix(),
            total_cards=1,
            columns=["word"],
        )
        mock_rerun.return_value = {
            "dataset": {
                "dataset_id": str(dataset.id),
                "source_type": "upload",
                "source_label": "rerun-test",
                "total_cards": 1,
                "columns": ["word", "meaning_english"],
                "available_profiles": [],
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            "card": {
                "index": 0,
                "total": 1,
                "front": {
                    "word": "hello",
                    "pronunciation": "",
                    "part_of_speech": "",
                    "register": "",
                    "profile_id": "lotm_zh_en_es",
                    "timestamp": "",
                    "audio": "",
                },
                "back": {
                    "meaning_english": "generated",
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
                "raw_row": {"word": "hello"},
            },
            "rerun_mode": "full",
            "applied_transforms": [],
        }

        response = client.post(
            f"/api/flashcards/datasets/{dataset.id}/card/rerun",
            {
                "index": 0,
                "profile_filter": "",
                "mode": "full",
            },
            format="json",
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["card"]["back"]["meaning_english"] == "generated"
        assert payload["rerun_mode"] == "full"
        mock_rerun.assert_called_once_with(
            dataset_id=str(dataset.id),
            owner=user,
            index=0,
            profile_filter="",
            mode="full",
        )
    finally:
        dataset_csv.unlink(missing_ok=True)


@pytest.mark.django_db
@patch("pipeline_api.views.upload_flashcard_card_custom_image")
def test_flashcard_card_upload_image_endpoint_calls_service(
    mock_upload_image,
    authenticated_api_client,
):
    client, user, _token = authenticated_api_client
    dataset_csv = Path("tests") / "_tmp_artifacts" / f"reviewer_upload_{uuid4().hex}.csv"
    dataset_csv.parent.mkdir(parents=True, exist_ok=True)
    dataset_csv.write_text("word\nhello\n", encoding="utf-8")

    try:
        dataset = FlashcardDataset.objects.create(
            owner=user,
            source_type=FlashcardDatasetSourceType.UPLOAD,
            source_label="upload-test",
            csv_path=dataset_csv.as_posix(),
            total_cards=1,
            columns=["word"],
        )
        mock_upload_image.return_value = {
            "dataset": {
                "dataset_id": str(dataset.id),
                "source_type": "upload",
                "source_label": "upload-test",
                "total_cards": 1,
                "columns": ["word", "picture"],
                "available_profiles": [],
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            "card": {
                "index": 0,
                "total": 1,
                "front": {
                    "word": "hello",
                    "pronunciation": "",
                    "part_of_speech": "",
                    "register": "",
                    "profile_id": "",
                    "timestamp": "",
                    "audio": "",
                },
                "back": {
                    "meaning_english": "",
                    "meaning_spanish": "",
                    "details": {},
                    "relationships": {"synonyms": [], "antonyms": [], "collocations": []},
                    "sentences": [],
                    "image": {
                        "picture": "media/flashcard_custom_images/file.png",
                        "image_term_type": "",
                        "visual_description": "",
                        "master_image_prompt": "",
                        "image_generation_skip_reason": "",
                        "image_render_status": "custom_upload",
                        "image_render_skip_reason": "",
                    },
                },
                "raw_row": {"word": "hello", "picture": "media/flashcard_custom_images/file.png"},
            },
        }

        response = client.post(
            f"/api/flashcards/datasets/{dataset.id}/card/upload-image",
            {
                "index": 0,
                "profile_filter": "",
                "image_file": SimpleUploadedFile(
                    "custom.png",
                    b"\x89PNG\r\n\x1a\n",
                    content_type="image/png",
                ),
            },
            format="multipart",
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["card"]["back"]["image"]["picture"]
        mock_upload_image.assert_called_once()
    finally:
        dataset_csv.unlink(missing_ok=True)


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
