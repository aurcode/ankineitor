from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient


@pytest.mark.django_db
@patch("pipeline_api.views.get_anki_presets")
def test_get_anki_presets(mock_get_anki_presets):
    mock_get_anki_presets.return_value = {
        "default": {"model_name": "Default"},
        "chinese_pipeline": {"model_name": "Chinese"},
    }

    client = APIClient()
    response = client.get("/api/anki/presets")

    assert response.status_code == 200
    payload = response.json()
    assert payload["default"]["model_name"] == "Default"
    assert payload["chinese_pipeline"]["model_name"] == "Chinese"


@pytest.mark.django_db
@patch("pipeline_api.views.generate_anki_deck_artifact")
def test_generate_anki_deck_returns_download_url(mock_generate):
    artifact_id = uuid4()
    mock_generate.return_value = SimpleNamespace(
        id=artifact_id,
        deck_name="My Deck",
        source_csv_name="cards.csv",
        file_size_bytes=512,
        created_at=datetime.now(timezone.utc),
    )

    upload = SimpleUploadedFile(
        "cards.csv",
        b"word,translation\nhello,hola\n",
        content_type="text/csv",
    )

    client = APIClient()
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

    assert response.status_code == 201
    payload = response.json()
    assert payload["artifact_id"] == str(artifact_id)
    assert payload["download_url"].endswith(f"/api/anki/decks/{artifact_id}/download")


@pytest.mark.django_db
def test_flashcards_saved_files_requires_profile_id():
    client = APIClient()
    response = client.get("/api/flashcards/saved-files")

    assert response.status_code == 400
    assert "profile_id" in response.json()["detail"]


@pytest.mark.django_db
@patch("pipeline_api.views.create_flashcard_dataset_from_saved")
def test_flashcards_dataset_from_saved(mock_create):
    mock_create.return_value = {
        "dataset_id": str(uuid4()),
        "source_type": "saved",
        "source_label": "profile:file.csv",
        "total_cards": 10,
        "columns": ["word"],
        "available_profiles": ["lotm_zh_en_es"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    client = APIClient()
    response = client.post(
        "/api/flashcards/datasets/from-saved",
        {"profile_id": "lotm_zh_en_es", "file_name": "file.csv"},
        format="json",
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["source_type"] == "saved"
    assert payload["total_cards"] == 10


@pytest.mark.django_db
@patch("pipeline_api.views.analyze_word_extractor")
def test_word_extractor_analyze_endpoint(mock_analyze):
    mock_analyze.return_value = {
        "initial_words": [{"word": "你好", "frequency": 3}],
        "filtered_words": [{"word": "你好", "frequency": 3}],
        "removed_words": [],
        "final_words": [{"word": "你好", "frequency": 3}],
        "copyable_word_list": "你好",
        "extraction_errors": {},
        "summary": {
            "initial_count": 1,
            "filtered_count": 1,
            "removed_count": 0,
            "final_count": 1,
            "min_frequency": 2,
            "applied_hsk_levels": ["hsk1"],
        },
    }

    client = APIClient()
    response = client.post(
        "/api/word-extractor/analyze",
        {
            "text_input": "你好你好你好",
            "selected_hsk_levels": ["hsk1"],
            "min_frequency": 2,
        },
        format="multipart",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["initial_count"] == 1
    assert payload["copyable_word_list"] == "你好"
