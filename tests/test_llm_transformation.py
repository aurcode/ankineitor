"""Unit tests for Gemini-backed LLM transformation."""

from unittest.mock import Mock, patch

import pandas as pd
import pytest

from ankineitor.pipeline.llm_transformation import (
    ExampleSentences,
    LLMTransformation,
    WordMeaning,
)
from ankineitor.security.exceptions import ValidationError


class TestLLMTransformationInit:
    def test_valid_token_initialization(self, mock_settings):
        mock_db_client = Mock()
        mock_settings.resolve_llm_api_token.return_value = "AQ.test_token_123"

        with patch(
            "ankineitor.pipeline.llm_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMTransformation, "_build_genai_client", return_value=Mock()
            ):
                transformation = LLMTransformation(
                    db_client=mock_db_client,
                    api_key="AQ.test_token_123",
                )
                assert transformation.api_key == "AQ.test_token_123"

    def test_missing_credentials_raises_validation_error(self, mock_settings):
        mock_db_client = Mock()
        mock_settings.resolve_llm_api_token.return_value = None
        mock_settings.bq_credentials_path = None
        mock_settings.vertex_credentials_path = None

        with patch(
            "ankineitor.pipeline.llm_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMTransformation, "_build_genai_client", side_effect=Exception("no creds")
            ):
                with pytest.raises(ValidationError, match="Gemini credentials are required"):
                    LLMTransformation(db_client=mock_db_client)

    def test_model_name_from_settings(self, mock_settings):
        mock_db_client = Mock()
        mock_settings.llm_model = "vertex_ai/gemini-3-flash-preview"

        with patch(
            "ankineitor.pipeline.llm_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMTransformation, "_build_genai_client", return_value=Mock()
            ):
                transformation = LLMTransformation(db_client=mock_db_client)
                assert transformation.model_name == "gemini-3-flash-preview"


class TestLLMTransformationProcess:
    def test_column_name_property(self, mock_settings):
        mock_db_client = Mock()

        with patch(
            "ankineitor.pipeline.llm_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMTransformation, "_build_genai_client", return_value=Mock()
            ):
                transformation = LLMTransformation(db_client=mock_db_client)
                assert transformation.column_name == "meaning_english"

    def test_language_profile_for_chinese_is_fixed_to_en_es(self, mock_settings):
        mock_db_client = Mock()

        with patch(
            "ankineitor.pipeline.llm_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMTransformation, "_build_genai_client", return_value=Mock()
            ):
                transformation = LLMTransformation(db_client=mock_db_client)
                profile = transformation._resolve_language_profile("谢谢")
                assert profile["is_chinese"] is True
                assert profile["primary_target_language"] == "English"
                assert profile["secondary_target_language"] == "Spanish"

    def test_language_profile_for_non_chinese_uses_config(self, mock_settings):
        mock_db_client = Mock()
        mock_settings.llm_source_language = "Spanish"
        mock_settings.llm_target_language = "English"
        mock_settings.llm_secondary_target_language = None

        with patch(
            "ankineitor.pipeline.llm_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMTransformation, "_build_genai_client", return_value=Mock()
            ):
                transformation = LLMTransformation(db_client=mock_db_client)
                profile = transformation._resolve_language_profile("gracias")
                assert profile["is_chinese"] is False
                assert profile["source_language"] == "Spanish"
                assert profile["primary_target_language"] == "English"
                assert profile["secondary_target_language"] is None

    def test_non_chinese_prompt_mentions_configured_languages(self, mock_settings):
        mock_db_client = Mock()
        mock_settings.llm_source_language = "Spanish"
        mock_settings.llm_target_language = "English"
        mock_settings.llm_secondary_target_language = "French"

        with patch(
            "ankineitor.pipeline.llm_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMTransformation, "_build_genai_client", return_value=Mock()
            ):
                transformation = LLMTransformation(db_client=mock_db_client)
                profile = transformation._resolve_language_profile("hola")
                prompt = transformation._build_meaning_prompt("hola", profile)
                assert "in English and French" in prompt

    def test_process_word_empty_returns_none(self, mock_settings):
        mock_db_client = Mock()

        with patch(
            "ankineitor.pipeline.llm_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMTransformation, "_build_genai_client", return_value=Mock()
            ):
                transformation = LLMTransformation(db_client=mock_db_client)
                assert transformation.process_word("") is None
                assert transformation.process_word("   ") is None

    def test_cache_hit_avoids_generation(self, mock_settings):
        mock_db_client = Mock()
        mock_db_client.find_record.return_value = {
            "word": "你好",
            "sentence_1": "你好，世界。",
            "sentence_2": "你好，朋友。",
            "sentence_3": "你好，今天。",
            "meaning_english": "hello",
            "meaning_spanish": "hola",
        }

        with patch(
            "ankineitor.pipeline.llm_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMTransformation, "_build_genai_client", return_value=Mock()
            ):
                transformation = LLMTransformation(db_client=mock_db_client)
                with patch.object(transformation, "_generate_structured_output") as mock_generate:
                    result = transformation.process_word("你好")
                    assert result is not None
                    assert result["meaning_english"] == "hello"
                    mock_generate.assert_not_called()

    def test_non_chinese_meaning_mapping_defaults_to_primary(self, mock_settings):
        mock_db_client = Mock()
        mock_db_client.find_record.return_value = None
        mock_settings.llm_source_language = "Spanish"
        mock_settings.llm_target_language = "French"
        mock_settings.llm_secondary_target_language = None

        with patch(
            "ankineitor.pipeline.llm_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMTransformation, "_build_genai_client", return_value=Mock()
            ):
                transformation = LLMTransformation(db_client=mock_db_client)

                def mock_generate(prompt, response_model):
                    if response_model is ExampleSentences:
                        return ExampleSentences(
                            sentence_1="Hola, mundo.",
                            sentence_2="Gracias por venir.",
                            sentence_3="Esto es una prueba.",
                        )
                    if response_model is WordMeaning:
                        return WordMeaning(english="merci", spanish="")
                    raise ValueError("unexpected response model")

                with patch.object(
                    transformation,
                    "_generate_structured_output",
                    side_effect=mock_generate,
                ):
                    result = transformation.process_word("gracias")
                    assert result is not None
                    assert result["meaning_english"] == "merci"
                    assert result["meaning_spanish"] is None

    def test_cache_miss_generates_and_saves(self, mock_settings):
        mock_db_client = Mock()
        mock_db_client.find_record.return_value = None

        with patch(
            "ankineitor.pipeline.llm_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMTransformation, "_build_genai_client", return_value=Mock()
            ):
                transformation = LLMTransformation(db_client=mock_db_client)

                def mock_generate(prompt, response_model):
                    if response_model is ExampleSentences:
                        return ExampleSentences(
                            sentence_1="你好，世界。",
                            sentence_2="你好，朋友。",
                            sentence_3="你好，今天。",
                        )
                    if response_model is WordMeaning:
                        return WordMeaning(english="hello", spanish="hola")
                    raise ValueError("unexpected response model")

                with patch.object(
                    transformation,
                    "_generate_structured_output",
                    side_effect=mock_generate,
                ):
                    result = transformation.process_word("你好")
                    assert result is not None
                    assert result["word"] == "你好"
                    assert result["meaning_english"] == "hello"
                    assert result["meaning_spanish"] == "hola"
                    mock_db_client.insert_record.assert_called_once()

    def test_process_word_handles_generation_error(self, mock_settings):
        mock_db_client = Mock()
        mock_db_client.find_record.return_value = None

        with patch(
            "ankineitor.pipeline.llm_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMTransformation, "_build_genai_client", return_value=Mock()
            ):
                transformation = LLMTransformation(db_client=mock_db_client)
                with patch.object(
                    transformation,
                    "_generate_structured_output",
                    side_effect=RuntimeError("boom"),
                ):
                    assert transformation.process_word("你好") is None


class TestLLMTransformationApply:
    def test_apply_requires_word_column(self, mock_settings):
        mock_db_client = Mock()

        with patch(
            "ankineitor.pipeline.llm_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMTransformation, "_build_genai_client", return_value=Mock()
            ):
                transformation = LLMTransformation(db_client=mock_db_client)
                df = pd.DataFrame({"other_column": ["test"]})
                result = transformation.apply(df)
                assert result.equals(df)

    def test_apply_with_no_successful_results_returns_original(self, mock_settings):
        mock_db_client = Mock()

        with patch(
            "ankineitor.pipeline.llm_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMTransformation, "_build_genai_client", return_value=Mock()
            ):
                transformation = LLMTransformation(db_client=mock_db_client)
                transformation.process_word = Mock(return_value=None)
                df = pd.DataFrame({"word": ["你好", "谢谢"]})
                result = transformation.apply(df)
                assert result.equals(df)

    def test_apply_with_partial_results_merges_output(self, mock_settings):
        mock_db_client = Mock()

        with patch(
            "ankineitor.pipeline.llm_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMTransformation, "_build_genai_client", return_value=Mock()
            ):
                transformation = LLMTransformation(db_client=mock_db_client)

                def mock_process(word):
                    if word == "你好":
                        return {
                            "word": "你好",
                            "sentence_1": "你好，世界。",
                            "sentence_2": "你好，朋友。",
                            "sentence_3": "你好，今天。",
                            "meaning_english": "hello",
                            "meaning_spanish": "hola",
                        }
                    return None

                transformation.process_word = mock_process
                df = pd.DataFrame({"word": ["你好", "谢谢"]})
                result = transformation.apply(df)
                assert len(result) == 2
                assert "meaning_english" in result.columns
                assert (
                    result.loc[result["word"] == "你好", "meaning_english"].iloc[0]
                    == "hello"
                )

    def test_apply_omits_secondary_column_when_all_values_empty(self, mock_settings):
        mock_db_client = Mock()

        with patch(
            "ankineitor.pipeline.llm_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMTransformation, "_build_genai_client", return_value=Mock()
            ):
                transformation = LLMTransformation(db_client=mock_db_client)

                transformation.process_word = Mock(
                    side_effect=lambda word: {
                        "word": word,
                        "sentence_1": f"{word} s1",
                        "sentence_2": f"{word} s2",
                        "sentence_3": f"{word} s3",
                        "meaning_english": f"{word} meaning",
                        "meaning_spanish": None,
                    }
                )

                df = pd.DataFrame({"word": ["hola", "adios"]})
                result = transformation.apply(df)

                assert "meaning_english" in result.columns
                assert "meaning_spanish" not in result.columns
