"""Unit tests for stage-1 Gemini image prompt transformation."""

from unittest.mock import Mock, patch

import pandas as pd
import pytest

from ankineitor.pipeline.llm_image_prompt_transformation import (
    LLMImagePromptTransformation,
    MASTER_IMAGE_PROMPT_TEMPLATE,
    VisualPromptPayload,
)
from ankineitor.security.exceptions import ValidationError


class TestLLMImagePromptTransformationInit:
    def test_valid_token_initialization(self, mock_settings):
        mock_db_client = Mock()
        mock_settings.resolve_llm_api_token.return_value = "AQ.test_token_123"

        with patch(
            "ankineitor.pipeline.llm_image_prompt_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMImagePromptTransformation, "_build_genai_client", return_value=Mock()
            ):
                transformation = LLMImagePromptTransformation(db_client=mock_db_client)
                assert transformation.model_name == "gemini-3.1-pro-preview"
                assert transformation.column_name == "master_image_prompt"
                assert "与" in transformation.blocked_terms
                assert transformation.source_language == "Chinese (Simplified)"

    def test_missing_credentials_raises_validation_error(self, mock_settings):
        mock_db_client = Mock()
        mock_settings.resolve_llm_api_token.return_value = None
        mock_settings.bq_credentials_path = None
        mock_settings.vertex_credentials_path = None

        with patch(
            "ankineitor.pipeline.llm_image_prompt_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMImagePromptTransformation,
                "_build_genai_client",
                side_effect=Exception("no creds"),
            ):
                with pytest.raises(
                    ValidationError,
                    match="Gemini credentials are required for image prompt generation",
                ):
                    LLMImagePromptTransformation(db_client=mock_db_client)


class TestLLMImagePromptTransformationProcess:
    def _build_transformation(self, mock_settings):
        mock_db_client = Mock()
        mock_db_client.find_record.return_value = None
        with patch(
            "ankineitor.pipeline.llm_image_prompt_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMImagePromptTransformation, "_build_genai_client", return_value=Mock()
            ):
                transformation = LLMImagePromptTransformation(db_client=mock_db_client)
        return transformation, mock_db_client

    def test_process_word_blocked_term_returns_skip_result(self, mock_settings):
        transformation, mock_db_client = self._build_transformation(mock_settings)
        result = transformation.process_word("与")

        assert result is not None
        assert result["word"] == "与"
        assert result["master_image_prompt"] is None
        assert result["image_generation_skip_reason"] == "blocked_by_do_not_generate_list"
        mock_db_client.insert_record.assert_called_once()

    def test_process_word_cache_hit_avoids_generation(self, mock_settings):
        transformation, mock_db_client = self._build_transformation(mock_settings)
        mock_db_client.find_record.return_value = {
            "word": "cache-key",
            "image_term_type": "concrete_noun",
            "visual_description": "cached description",
            "master_image_prompt": "cached prompt",
            "image_generation_skip_reason": None,
        }

        with patch.object(transformation, "_generate_structured_output") as mock_generate:
            result = transformation.process_word("左轮手枪")
            assert result is not None
            assert result["master_image_prompt"] == "cached prompt"
            mock_generate.assert_not_called()

    def test_process_word_cache_miss_generates_and_saves(self, mock_settings):
        transformation, mock_db_client = self._build_transformation(mock_settings)

        with patch.object(
            transformation,
            "_generate_structured_output",
            return_value=VisualPromptPayload(
                image_term_type="noun",
                visual_description="a worn antique Victorian revolver with tarnished brass engravings",
            ),
        ):
            result = transformation.process_word("左轮手枪")

        assert result is not None
        assert result["word"] == "左轮手枪"
        assert result["image_term_type"] == "concrete_noun"
        assert "#F8F5EE" in result["master_image_prompt"]
        assert result["master_image_prompt"].startswith(
            "A highly detailed, conceptual illustration"
        )
        assert result["image_generation_skip_reason"] is None
        mock_db_client.insert_record.assert_called_once()

    def test_format_master_prompt_uses_default_template(self, mock_settings):
        transformation, _ = self._build_transformation(mock_settings)
        master_prompt = transformation._format_master_prompt("test scene")
        assert master_prompt == MASTER_IMAGE_PROMPT_TEMPLATE.format(
            visual_description="test scene"
        )

    def test_build_visual_prompt_adds_russian_victorian_hint(self, mock_settings):
        transformation, _ = self._build_transformation(mock_settings)
        transformation.source_language = "Russian"

        prompt = transformation._build_visual_prompt("набережная")

        assert "Saint Petersburg canals" in prompt
        assert "Victorian gaslamp aesthetic" in prompt

    def test_cache_key_changes_by_source_language(self, mock_settings):
        transformation, _ = self._build_transformation(mock_settings)
        key_zh = transformation._build_cache_key_word("мост")
        transformation.source_language = "Russian"
        key_ru = transformation._build_cache_key_word("мост")
        assert key_ru != key_zh


class TestLLMImagePromptTransformationApply:
    def _build_transformation(self, mock_settings):
        mock_db_client = Mock()
        with patch(
            "ankineitor.pipeline.llm_image_prompt_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMImagePromptTransformation, "_build_genai_client", return_value=Mock()
            ):
                transformation = LLMImagePromptTransformation(db_client=mock_db_client)
        return transformation

    def test_apply_requires_word_column(self, mock_settings):
        transformation = self._build_transformation(mock_settings)
        df = pd.DataFrame({"other": ["x"]})
        result = transformation.apply(df)
        assert result.equals(df)

    def test_apply_with_partial_results_merges_output(self, mock_settings):
        transformation = self._build_transformation(mock_settings)
        transformation.process_word = Mock(
            side_effect=lambda word: (
                {
                    "word": "cat",
                    "image_term_type": "concrete_noun",
                    "visual_description": "a dark mahogany cat bust",
                    "master_image_prompt": "master prompt for cat",
                    "image_generation_skip_reason": None,
                }
                if word == "cat"
                else None
            )
        )

        df = pd.DataFrame({"word": ["cat", "dog"]})
        result = transformation.apply(df)

        assert "master_image_prompt" in result.columns
        assert (
            result.loc[result["word"] == "cat", "master_image_prompt"].iloc[0]
            == "master prompt for cat"
        )
        assert pd.isna(
            result.loc[result["word"] == "dog", "master_image_prompt"].iloc[0]
        )
