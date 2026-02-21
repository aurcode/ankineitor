"""Unit tests for Gemini image transformation."""

import base64
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from ankineitor.pipeline.llm_image_transformation import (
    IMAGE_RENDER_SKIP_REASON_COLUMN,
    IMAGE_RENDER_STATUS_COLUMN,
    LLMImageTransformation,
)
from ankineitor.security.exceptions import ValidationError


class TestLLMImageTransformationInit:
    def test_valid_token_initialization(self, mock_settings, temp_dir):
        mock_settings.resolve_llm_api_token.return_value = "AQ.test_token_123"
        mock_settings.image_output_dir = str(temp_dir / "images")

        with patch(
            "ankineitor.pipeline.llm_image_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMImageTransformation, "_build_genai_client", return_value=Mock()
            ):
                transformation = LLMImageTransformation()
                assert transformation.model_name == "gemini-3-pro-image-preview"
                assert transformation.output_dir == Path(mock_settings.image_output_dir)
                assert transformation.max_workers == 1

    def test_missing_credentials_raises_validation_error(self, mock_settings):
        mock_settings.resolve_llm_api_token.return_value = None
        mock_settings.bq_credentials_path = None
        mock_settings.vertex_credentials_path = None

        with patch(
            "ankineitor.pipeline.llm_image_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMImageTransformation,
                "_build_genai_client",
                side_effect=Exception("no creds"),
            ):
                with pytest.raises(
                    ValidationError,
                    match="Gemini credentials are required for image generation",
                ):
                    LLMImageTransformation()

    def test_uses_fallback_output_dir_when_primary_is_not_writable(
        self, mock_settings, temp_dir
    ):
        mock_settings.image_output_dir = str(temp_dir / "images")
        with patch(
            "ankineitor.pipeline.llm_image_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMImageTransformation, "_build_genai_client", return_value=Mock()
            ):
                with patch(
                    "ankineitor.pipeline.llm_image_transformation._directory_is_writable",
                    side_effect=[False, True],
                ):
                    transformation = LLMImageTransformation()

        assert transformation.output_dir == transformation.fallback_output_dir


class TestLLMImageTransformationProcess:
    def _build_transformation(self, mock_settings, temp_dir):
        mock_settings.image_output_dir = str(temp_dir / "images")
        with patch(
            "ankineitor.pipeline.llm_image_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMImageTransformation, "_build_genai_client", return_value=Mock()
            ):
                return LLMImageTransformation()

    def test_column_name_property(self, mock_settings, temp_dir):
        transformation = self._build_transformation(mock_settings, temp_dir)
        assert transformation.column_name == "picture"

    def test_build_prompt_uses_master_prompt(self, mock_settings, temp_dir):
        transformation = self._build_transformation(mock_settings, temp_dir)
        prompt = transformation._build_prompt("  full master prompt  ")
        assert prompt == "full master prompt"

    def test_extract_image_bytes_from_response(self, mock_settings, temp_dir):
        transformation = self._build_transformation(mock_settings, temp_dir)
        response = SimpleNamespace(
            candidates=[
                SimpleNamespace(
                    content=SimpleNamespace(
                        parts=[
                            SimpleNamespace(
                                inline_data=SimpleNamespace(
                                    data=b"fake-image", mime_type="image/png"
                                )
                            )
                        ]
                    )
                )
            ]
        )
        image_bytes, mime_type = transformation._extract_image_bytes(response)
        assert image_bytes == b"fake-image"
        assert mime_type == "image/png"

    def test_extract_image_bytes_from_base64_string(self, mock_settings, temp_dir):
        transformation = self._build_transformation(mock_settings, temp_dir)
        payload = base64.b64encode(b"another-image").decode("utf-8")
        response = SimpleNamespace(
            candidates=[
                SimpleNamespace(
                    content=SimpleNamespace(
                        parts=[
                            SimpleNamespace(
                                inline_data={"data": payload, "mime_type": "image/jpeg"}
                            )
                        ]
                    )
                )
            ]
        )
        image_bytes, mime_type = transformation._extract_image_bytes(response)
        assert image_bytes == b"another-image"
        assert mime_type == "image/jpeg"

    def test_process_word_uses_cached_image(self, mock_settings, temp_dir):
        transformation = self._build_transformation(mock_settings, temp_dir)
        master_prompt = "master prompt for apple"
        cache_key = transformation._cache_key("apple", master_prompt)
        cached_path = transformation.output_dir / f"{cache_key}.png"
        cached_path.write_bytes(b"cached")

        with patch.object(transformation, "_generate_image") as mock_generate:
            result = transformation.process_word("apple", master_prompt)
            assert result == {
                "word": "apple",
                "picture": str(cached_path),
                "image_render_status": "cached",
                "image_render_skip_reason": None,
            }
            mock_generate.assert_not_called()

    def test_process_word_generates_and_saves_image(self, mock_settings, temp_dir):
        transformation = self._build_transformation(mock_settings, temp_dir)
        with patch.object(
            transformation, "_generate_image", return_value=(b"new-bytes", "image/png")
        ):
            result = transformation.process_word("banana", "master prompt for banana")

        assert result is not None
        file_path = Path(result["picture"])
        assert file_path.exists()
        assert file_path.read_bytes() == b"new-bytes"
        assert result[IMAGE_RENDER_STATUS_COLUMN] == "generated"
        assert result[IMAGE_RENDER_SKIP_REASON_COLUMN] is None

    def test_process_word_returns_skip_result_when_missing_master_prompt(
        self, mock_settings, temp_dir
    ):
        transformation = self._build_transformation(mock_settings, temp_dir)
        result = transformation.process_word("banana", None)
        assert result is not None
        assert result["word"] == "banana"
        assert result["picture"] is None
        assert result[IMAGE_RENDER_STATUS_COLUMN] == "skipped"
        assert (
            result[IMAGE_RENDER_SKIP_REASON_COLUMN] == "missing_master_image_prompt"
        )

    def test_process_word_falls_back_when_primary_output_dir_loses_write_access(
        self, mock_settings, temp_dir
    ):
        transformation = self._build_transformation(mock_settings, temp_dir)
        fallback_dir = temp_dir / "fallback_images"
        fallback_dir.mkdir(parents=True, exist_ok=True)
        transformation.fallback_output_dir = fallback_dir

        # Simulate permission drift after startup.
        transformation.output_dir.chmod(0o555)
        try:
            with patch.object(
                transformation,
                "_generate_image",
                return_value=(b"fallback-bytes", "image/png"),
            ):
                result = transformation.process_word("naranja", "master prompt")
        finally:
            transformation.output_dir.chmod(0o755)

        assert result is not None
        generated_path = Path(result["picture"])
        assert generated_path.parent == fallback_dir
        assert generated_path.exists()
        assert generated_path.read_bytes() == b"fallback-bytes"


class TestLLMImageTransformationApply:
    def _build_transformation(self, mock_settings, temp_dir):
        mock_settings.image_output_dir = str(temp_dir / "images")
        with patch(
            "ankineitor.pipeline.llm_image_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMImageTransformation, "_build_genai_client", return_value=Mock()
            ):
                return LLMImageTransformation()

    def test_apply_requires_word_column(self, mock_settings, temp_dir):
        transformation = self._build_transformation(mock_settings, temp_dir)
        df = pd.DataFrame({"other": ["x"]})
        result = transformation.apply(df)
        assert result.equals(df)

    def test_apply_with_partial_results_merges_output(self, mock_settings, temp_dir):
        transformation = self._build_transformation(mock_settings, temp_dir)
        transformation.process_word = Mock(
            side_effect=lambda word, prompt, skip_reason=None: (
                {
                    "word": "cat",
                    "picture": "/tmp/cat.png",
                    "image_render_status": "generated",
                    "image_render_skip_reason": None,
                }
                if word == "cat"
                else {
                    "word": "dog",
                    "picture": None,
                    "image_render_status": "skipped",
                    "image_render_skip_reason": "blocked",
                }
            )
        )

        df = pd.DataFrame(
            {
                "word": ["cat", "dog"],
                "master_image_prompt": ["prompt cat", "prompt dog"],
            }
        )
        result = transformation.apply(df)

        assert "picture" in result.columns
        assert result.loc[result["word"] == "cat", "picture"].iloc[0] == "/tmp/cat.png"
        assert pd.isna(result.loc[result["word"] == "dog", "picture"].iloc[0])
        assert (
            result.loc[result["word"] == "dog", "image_render_status"].iloc[0]
            == "skipped"
        )

    def test_apply_processes_unique_words_once(self, mock_settings, temp_dir):
        transformation = self._build_transformation(mock_settings, temp_dir)
        transformation.max_workers = 1

        calls = []

        def fake_process(word, prompt, skip_reason=None):
            calls.append((word, prompt, skip_reason))
            return {
                "word": word,
                "picture": f"/tmp/{word}.png",
                "image_render_status": "generated",
                "image_render_skip_reason": None,
            }

        transformation.process_word = Mock(side_effect=fake_process)

        df = pd.DataFrame(
            {
                "word": ["cat", "cat", "dog"],
                "master_image_prompt": ["prompt cat", "prompt cat", "prompt dog"],
            }
        )
        result = transformation.apply(df)

        assert calls == [("cat", "prompt cat", None), ("dog", "prompt dog", None)]
        assert "picture" in result.columns
        assert len(result) == 2

    def test_apply_marks_rows_skipped_when_master_prompt_column_is_missing(
        self, mock_settings, temp_dir
    ):
        transformation = self._build_transformation(mock_settings, temp_dir)
        df = pd.DataFrame({"word": ["cat"]})
        result = transformation.apply(df)
        assert result.loc[result["word"] == "cat", IMAGE_RENDER_STATUS_COLUMN].iloc[0] == "skipped"
        assert (
            result.loc[result["word"] == "cat", IMAGE_RENDER_SKIP_REASON_COLUMN].iloc[0]
            == "missing_master_image_prompt"
        )
