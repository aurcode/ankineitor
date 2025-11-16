"""Unit tests for LLM transformation security improvements."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import pandas as pd

from ankineitor.pipeline.llm_transformation import LLMTransformation
from ankineitor.security.exceptions import ValidationError


class TestLLMTransformationSecurity:
    """Test LLM transformation security features."""

    def test_valid_api_key_initialization(self, mock_settings):
        """Test initialization with valid API key."""
        mock_db_client = Mock()
        
        with patch('ankineitor.pipeline.llm_transformation.get_settings', return_value=mock_settings):
            transformation = LLMTransformation(
                db_client=mock_db_client,
                api_key="gsk_test_api_key_1234567890abcdef"
            )
            assert transformation.api_key == "gsk_test_api_key_1234567890abcdef"

    def test_missing_api_key_raises_error(self, mock_settings):
        """Test that missing API key raises ValidationError."""
        mock_settings.groq_api_key = None
        mock_db_client = Mock()
        
        with patch('ankineitor.pipeline.llm_transformation.get_settings', return_value=mock_settings):
            with pytest.raises(ValidationError, match="Groq API key is required"):
                LLMTransformation(db_client=mock_db_client)

    def test_invalid_api_key_format_raises_error(self, mock_settings):
        """Test that invalid API key format raises ValidationError."""
        mock_db_client = Mock()
        
        with patch('ankineitor.pipeline.llm_transformation.get_settings', return_value=mock_settings):
            with pytest.raises(ValidationError, match="Invalid Groq API key format"):
                LLMTransformation(
                    db_client=mock_db_client,
                    api_key="invalid_key_format"
                )

    def test_api_key_from_settings(self, mock_settings):
        """Test API key loaded from settings."""
        mock_db_client = Mock()
        
        with patch('ankineitor.pipeline.llm_transformation.get_settings', return_value=mock_settings):
            transformation = LLMTransformation(db_client=mock_db_client)
            assert transformation.api_key == "gsk_test_api_key_1234567890abcdef"

    def test_configurable_model_from_settings(self, mock_settings):
        """Test that model is loaded from settings."""
        mock_settings.llm_model = "custom-model-123"
        mock_db_client = Mock()
        
        with patch('ankineitor.pipeline.llm_transformation.get_settings', return_value=mock_settings):
            with patch('ankineitor.pipeline.llm_transformation.ChatGroq') as mock_chatgroq:
                transformation = LLMTransformation(db_client=mock_db_client)
                
                # Verify ChatGroq was called with the correct model
                mock_chatgroq.assert_called_once()
                call_args = mock_chatgroq.call_args
                assert call_args[1]['model'] == "custom-model-123"


class TestLLMTransformationFunctionality:
    """Test LLM transformation core functionality."""

    def test_column_name_property(self, mock_settings):
        """Test column name property."""
        mock_db_client = Mock()
        
        with patch('ankineitor.pipeline.llm_transformation.get_settings', return_value=mock_settings):
            transformation = LLMTransformation(db_client=mock_db_client)
            assert transformation.column_name == "meaning_english"

    def test_initialization_with_custom_retries(self, mock_settings):
        """Test initialization with custom retry settings."""
        mock_db_client = Mock()
        
        with patch('ankineitor.pipeline.llm_transformation.get_settings', return_value=mock_settings):
            transformation = LLMTransformation(
                db_client=mock_db_client,
                max_retries=5
            )
            assert transformation.max_retries == 5

    def test_initialization_with_custom_table(self, mock_settings):
        """Test initialization with custom table name."""
        mock_db_client = Mock()
        
        with patch('ankineitor.pipeline.llm_transformation.get_settings', return_value=mock_settings):
            transformation = LLMTransformation(
                db_client=mock_db_client,
                table_name="custom_table"
            )
            assert transformation.table_name == "custom_table"

    def test_apply_method_requires_word_column(self, mock_settings):
        """Test that apply method requires 'word' column."""
        mock_db_client = Mock()
        
        with patch('ankineitor.pipeline.llm_transformation.get_settings', return_value=mock_settings):
            transformation = LLMTransformation(db_client=mock_db_client)
            
            # DataFrame without 'word' column
            df = pd.DataFrame({'other_column': ['test']})
            result = transformation.apply(df)
            
            # Should return original DataFrame unchanged
            assert result.equals(df)

    def test_apply_method_with_empty_dataframe(self, mock_settings):
        """Test apply method with empty DataFrame."""
        mock_db_client = Mock()
        
        with patch('ankineitor.pipeline.llm_transformation.get_settings', return_value=mock_settings):
            transformation = LLMTransformation(db_client=mock_db_client)
            
            empty_df = pd.DataFrame(columns=['word'])
            result = transformation.apply(empty_df)
            
            assert result.empty


class TestLLMTransformationCaching:
    """Test LLM transformation caching functionality."""

    def test_cache_hit_avoids_api_call(self, mock_settings):
        """Test that cache hit avoids API call."""
        mock_db_client = Mock()
        mock_db_client.find_record.return_value = {
            "word": "你好",
            "sentence_1": "你好，世界。",
            "sentence_2": "你好，朋友。",
            "sentence_3": "你好，今天。",
            "meaning_english": "hello",
            "meaning_spanish": "hola"
        }
        
        with patch('ankineitor.pipeline.llm_transformation.get_settings', return_value=mock_settings):
            transformation = LLMTransformation(db_client=mock_db_client)
            result = transformation.process_word("你好")
            
            assert result is not None
            assert result["word"] == "你好"
            assert result["meaning_english"] == "hello"
            assert result["meaning_spanish"] == "hola"
            # API should not be called due to cache hit
            mock_db_client.find_record.assert_called_once()

    def test_cache_miss_triggers_api_call(self, mock_settings):
        """Test that cache miss triggers API call."""
        mock_db_client = Mock()
        mock_db_client.find_record.return_value = None
        
        # Mock successful API response
        mock_sentences = Mock()
        mock_sentences.model_dump.return_value = {
            "sentence_1": "你好，世界。",
            "sentence_2": "你好，朋友。",
            "sentence_3": "你好，今天。"
        }
        
        mock_meaning = Mock()
        mock_meaning.english = "hello"
        mock_meaning.spanish = "hola"
        
        with patch('ankineitor.pipeline.llm_transformation.get_settings', return_value=mock_settings):
            with patch('ankineitor.pipeline.llm_transformation.ChatGroq') as mock_chatgroq:
                # Mock the chain execution
                mock_chain = Mock()
                mock_chain.invoke.side_effect = [mock_sentences, mock_meaning]
                
                mock_llm = Mock()
                mock_llm.__or__ = Mock(return_value=mock_chain)
                
                mock_chatgroq.return_value = mock_llm
                
                transformation = LLMTransformation(db_client=mock_db_client)
                result = transformation.process_word("你好")
                
                assert result is not None
                assert result["word"] == "你好"
                assert result["meaning_english"] == "hello"
                assert result["meaning_spanish"] == "hola"
                
                # Verify API was called
                assert mock_chain.invoke.call_count == 2
                mock_db_client.insert_record.assert_called_once()


class TestLLMTransformationErrorHandling:
    """Test LLM transformation error handling."""

    def test_process_word_handles_api_errors(self, mock_settings):
        """Test that process_word handles API errors gracefully."""
        mock_db_client = Mock()
        mock_db_client.find_record.return_value = None
        
        with patch('ankineitor.pipeline.llm_transformation.get_settings', return_value=mock_settings):
            with patch('ankineitor.pipeline.llm_transformation.ChatGroq') as mock_chatgroq:
                # Mock API failure
                mock_chatgroq.side_effect = Exception("API Error")
                
                transformation = LLMTransformation(db_client=mock_db_client)
                result = transformation.process_word("你好")
                
                # Should return None on error
                assert result is None

    def test_apply_method_handles_empty_results(self, mock_settings):
        """Test apply method handles empty results gracefully."""
        mock_db_client = Mock()
        
        with patch('ankineitor.pipeline.llm_transformation.get_settings', return_value=mock_settings):
            transformation = LLMTransformation(db_client=mock_db_client)
            
            # Mock process_word to return None (failed processing)
            transformation.process_word = Mock(return_value=None)
            
            df = pd.DataFrame({'word': ['你好', '谢谢']})
            result = transformation.apply(df)
            
            # Should return original DataFrame when no results
            assert result.equals(df)

    def test_apply_method_with_partial_results(self, mock_settings):
        """Test apply method with partial results (some words fail)."""
        mock_db_client = Mock()
        
        with patch('ankineitor.pipeline.llm_transformation.get_settings', return_value=mock_settings):
            transformation = LLMTransformation(db_client=mock_db_client)
            
            # Mock process_word to return None for some words
            def mock_process_word(word):
                if word == "你好":
                    return {
                        "word": "你好",
                        "sentence_1": "你好，世界。",
                        "sentence_2": "你好，朋友。",
                        "sentence_3": "你好，今天。",
                        "meaning_english": "hello",
                        "meaning_spanish": "hola"
                    }
                else:
                    return None
            
            transformation.process_word = mock_process_word
            
            df = pd.DataFrame({'word': ['你好', '谢谢']})
            result = transformation.apply(df)
            
            # Should merge partial results
            assert len(result) == 2
            assert 'meaning_english' in result.columns
            assert result.loc[result['word'] == '你好', 'meaning_english'].iloc[0] == 'hello'


class TestLLMTransformationSecurityEdgeCases:
    """Test security edge cases."""

    def test_empty_word_handling(self, mock_settings):
        """Test handling of empty words."""
        mock_db_client = Mock()
        
        with patch('ankineitor.pipeline.llm_transformation.get_settings', return_value=mock_settings):
            transformation = LLMTransformation(db_client=mock_db_client)
            result = transformation.process_word("")
            
            # Should return None for empty words
            assert result is None

    def test_whitespace_word_handling(self, mock_settings):
        """Test handling of whitespace-only words."""
        mock_db_client = Mock()
        
        with patch('ankineitor.pipeline.llm_transformation.get_settings', return_value=mock_settings):
            transformation = LLMTransformation(db_client=mock_db_client)
            result = transformation.process_word("   ")
            
            # Should return None for whitespace-only words
            assert result is None

    def test_very_long_word_handling(self, mock_settings):
        """Test handling of very long words."""
        mock_db_client = Mock()
        long_word = "你" * 1000  # Very long Chinese word
        
        with patch('ankineitor.pipeline.llm_transformation.get_settings', return_value=mock_settings):
            transformation = LLMTransformation(db_client=mock_db_client)
            result = transformation.process_word(long_word)
            
            # Should handle long words without crashing
            assert result is None  # Will likely fail API validation

    def test_special_characters_in_word(self, mock_settings):
        """Test handling of words with special characters."""
        mock_db_client = Mock()
        
        with patch('ankineitor.pipeline.llm_transformation.get_settings', return_value=mock_settings):
            transformation = LLMTransformation(db_client=mock_db_client)
            
            # Test various special characters
            special_words = ["hello123", "test@word", "word_with_underscore"]
            for word in special_words:
                result = transformation.process_word(word)
                # Should handle without crashing
                assert result is None  # Will likely fail as not Chinese


class TestLLMTransformationRetryLogic:
    """Test retry logic functionality."""

    def test_retry_on_api_failure(self, mock_settings):
        """Test that retry logic works on API failure."""
        mock_db_client = Mock()
        mock_db_client.find_record.return_value = None
        
        with patch('ankineitor.pipeline.llm_transformation.get_settings', return_value=mock_settings):
            with patch('ankineitor.pipeline.llm_transformation.ChatGroq') as mock_chatgroq:
                # Mock API that fails initially then succeeds
                call_count = 0
                
                def mock_invoke(*args, **kwargs):
                    nonlocal call_count
                    call_count += 1
                    if call_count < 3:  # Fail first 2 attempts
                        raise Exception("API Error")
                    else:  # Succeed on third attempt
                        return Mock()
                
                mock_chain = Mock()
                mock_chain.invoke = mock_invoke
                
                mock_llm = Mock()
                mock_llm.__or__ = Mock(return_value=mock_chain)
                
                mock_chatgroq.return_value = mock_llm
                
                transformation = LLMTransformation(
                    db_client=mock_db_client,
                    max_retries=3
                )
                
                # This should succeed after retries
                result = transformation.process_word("你好")
                
                # Should have made 3 attempts (initial + 2 retries)
                assert call_count == 3


class TestLLMTransformationDataFrameHandling:
    """Test DataFrame handling in apply method."""

    def test_apply_with_duplicate_words(self, mock_settings):
        """Test apply method with duplicate words in DataFrame."""
        mock_db_client = Mock()
        
        with patch('ankineitor.pipeline.llm_transformation.get_settings', return_value=mock_settings):
            transformation = LLMTransformation(db_client=mock_db_client)
            
            # Mock successful processing
            transformation.process_word = Mock(return_value={
                "word": "你好",
                "sentence_1": "你好，世界。",
                "sentence_2": "你好，朋友。",
                "sentence_3": "你好，今天。",
                "meaning_english": "hello",
                "meaning_spanish": "hola"
            })
            
            # DataFrame with duplicate words
            df = pd.DataFrame({'word': ['你好', '你好', '谢谢']})
            result = transformation.apply(df)
            
            # Should handle duplicates correctly
            assert len(result) == 3
            assert 'meaning_english' in result.columns

    def test_apply_preserves_original_order(self, mock_settings):
        """Test that apply method preserves original DataFrame order."""
        mock_db_client = Mock()
        
        with patch('ankineitor.pipeline.llm_transformation.get_settings', return_value=mock_settings):
            transformation = LLMTransformation(db_client=mock_db_client)
            
            # Mock processing
            transformation.process_word = Mock(side_effect=lambda word: {
                "word": word,
                "meaning_english": f"meaning_of_{word}",
                "meaning_spanish": f"significado_de_{word}"
            } if word == "你好" else None)
            
            original_df = pd.DataFrame({'word': ['你好', '谢谢', '苹果']})
            result = transformation.apply(original_df)
            
            # Should preserve original order
            assert result['word'].tolist() == ['你好', '谢谢', '苹果']
