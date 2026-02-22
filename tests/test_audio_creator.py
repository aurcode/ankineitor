"""Unit tests for MiniMax-backed AudioCreator."""

from pathlib import Path
from unittest.mock import patch

from ankineitor.pipeline.audio_creator import AudioCreator


def test_resolve_tts_language_known_mapping(temp_dir):
    creator = AudioCreator(folder_name=str(temp_dir / "audio"))
    assert creator.resolve_tts_language("Spanish") == "es"
    assert creator.resolve_tts_language("Russian") == "ru"


def test_create_audio_writes_file_and_uses_cache(temp_dir):
    creator = AudioCreator(folder_name=str(temp_dir / "audio"))
    creator.minimax_api_token = "test-token"

    with patch.object(
        creator, "_request_tts_audio", return_value=b"fake-mp3-binary"
    ) as mock_request:
        first_path = creator._create_audio("hola mundo", language="Spanish")
        second_path = creator._create_audio("hola mundo", language="Spanish")

    assert first_path is not None
    assert second_path == first_path
    assert mock_request.call_count == 1
    assert Path(first_path).exists()
    assert Path(first_path).read_bytes() == b"fake-mp3-binary"
