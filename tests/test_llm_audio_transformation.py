import pytest
import pandas as pd
import os
import tempfile
from unittest.mock import Mock, patch

from ankineitor.pipeline.llm_audio_transformation import LLMAudioTransformation
from ankineitor.pipeline.audio_creator import AudioCreator


class TestLLMAudioTransformation:
    """Test suite for LLM Audio Transformation."""

    @pytest.fixture
    def temp_audio_dir(self):
        """Create a temporary directory for audio files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def audio_creator(self, temp_audio_dir):
        """Create an AudioCreator instance with temporary directory."""
        return AudioCreator(folder_name=temp_audio_dir)

    @pytest.fixture
    def llm_audio_transform(self, audio_creator):
        """Create an LLMAudioTransformation instance."""
        return LLMAudioTransformation(audio_creator=audio_creator)

    @pytest.fixture
    def sample_df_with_sentences(self):
        """Create a sample DataFrame with LLM sentences."""
        return pd.DataFrame({
            'word': ['你好', '谢谢'],
            'sentence_1': ['你好，今天天气很好。', '谢谢你帮助我。'],
            'sentence_2': ['你好，很高兴认识你。', '谢谢你的礼物。'],
            'sentence_3': ['你好，最近怎么样？', '非常感谢。'],
            'meaning_english': ['hello', 'thank you'],
            'meaning_spanish': ['hola', 'gracias']
        })

    @pytest.fixture
    def sample_df_without_sentences(self):
        """Create a sample DataFrame without sentence columns."""
        return pd.DataFrame({
            'word': ['你好', '谢谢'],
            'meaning_english': ['hello', 'thank you'],
            'meaning_spanish': ['hola', 'gracias']
        })

    def test_initialization(self, llm_audio_transform):
        """Test that the transformation initializes correctly."""
        assert llm_audio_transform.column_name == "sentence_1_audio"
        assert llm_audio_transform.audio_creator is not None
        assert llm_audio_transform.source_language == "Chinese (Simplified)"

    def test_apply_with_sentences(self, llm_audio_transform, sample_df_with_sentences):
        """Test applying transformation to DataFrame with sentences."""
        # Mock the audio creation to avoid actual API calls
        with patch.object(llm_audio_transform.audio_creator, '_create_audio') as mock_create_audio:
            mock_create_audio.return_value = "/fake/audio/path.mp3"
            
            result_df = llm_audio_transform.apply(sample_df_with_sentences)
            
            # Check that audio columns were added
            assert 'sentence_1_audio' in result_df.columns
            assert 'sentence_2_audio' in result_df.columns
            assert 'sentence_3_audio' in result_df.columns
            
            # Check that audio was created for each sentence
            assert mock_create_audio.call_count == 6  # 3 sentences × 2 words
            
            # Check that audio paths are in the result
            assert result_df['sentence_1_audio'].iloc[0] == "/fake/audio/path.mp3"
            assert result_df['sentence_2_audio'].iloc[0] == "/fake/audio/path.mp3"
            assert result_df['sentence_3_audio'].iloc[0] == "/fake/audio/path.mp3"

    def test_apply_without_sentences(self, llm_audio_transform, sample_df_without_sentences):
        """Test applying transformation to DataFrame without sentences."""
        result_df = llm_audio_transform.apply(sample_df_without_sentences)
        
        # Check that no audio columns were added
        assert 'sentence_1_audio' not in result_df.columns
        assert 'sentence_2_audio' not in result_df.columns
        assert 'sentence_3_audio' not in result_df.columns
        
        # DataFrame should remain unchanged
        pd.testing.assert_frame_equal(result_df, sample_df_without_sentences)

    def test_apply_with_empty_sentences(self, llm_audio_transform):
        """Test applying transformation with empty sentences."""
        df_with_empty = pd.DataFrame({
            'word': ['你好'],
            'sentence_1': [''],
            'sentence_2': [None],
            'sentence_3': ['   '],  # Whitespace only
        })
        
        result_df = llm_audio_transform.apply(df_with_empty)
        
        # Check that audio columns were added but contain None
        assert 'sentence_1_audio' in result_df.columns
        assert 'sentence_2_audio' in result_df.columns
        assert 'sentence_3_audio' in result_df.columns
        
        # All should be None since sentences are empty
        assert result_df['sentence_1_audio'].iloc[0] is None
        assert result_df['sentence_2_audio'].iloc[0] is None
        assert result_df['sentence_3_audio'].iloc[0] is None

    def test_create_sentence_audio_success(self, llm_audio_transform):
        """Test successful audio creation for a sentence."""
        with patch.object(llm_audio_transform.audio_creator, '_create_audio') as mock_create_audio:
            mock_create_audio.return_value = "/fake/audio/sentence.mp3"
            
            result = llm_audio_transform._create_sentence_audio("你好，世界。")
            
            assert result == "/fake/audio/sentence.mp3"
            mock_create_audio.assert_called_once_with("你好，世界。", language=None)

    def test_create_sentence_audio_empty(self, llm_audio_transform):
        """Test audio creation with empty sentence."""
        result = llm_audio_transform._create_sentence_audio("")
        assert result is None
        
        result = llm_audio_transform._create_sentence_audio("   ")
        assert result is None
        
        result = llm_audio_transform._create_sentence_audio(None)
        assert result is None

    def test_create_sentence_audio_error(self, llm_audio_transform):
        """Test audio creation when an error occurs."""
        with patch.object(llm_audio_transform.audio_creator, '_create_audio') as mock_create_audio:
            mock_create_audio.side_effect = Exception("Audio creation failed")
            
            result = llm_audio_transform._create_sentence_audio("你好，世界。")
            
            assert result is None

    def test_partial_sentence_columns(self, llm_audio_transform):
        """Test with only some sentence columns present."""
        df_partial = pd.DataFrame({
            'word': ['你好'],
            'sentence_1': ['你好，世界。'],
            'sentence_3': ['最近怎么样？'],
            # sentence_2 is missing
        })
        
        with patch.object(llm_audio_transform.audio_creator, '_create_audio') as mock_create_audio:
            mock_create_audio.return_value = "/fake/audio/path.mp3"
            
            result_df = llm_audio_transform.apply(df_partial)
            
            # Check that only available sentence audio columns were added
            assert 'sentence_1_audio' in result_df.columns
            assert 'sentence_2_audio' not in result_df.columns  # Should not be created
            assert 'sentence_3_audio' in result_df.columns
            
            # Check that audio was created for existing sentences
            assert mock_create_audio.call_count == 2  # Only sentence_1 and sentence_3

    def test_apply_resolves_audio_language_from_source(self, llm_audio_transform):
        """Test sentence audio uses source-language-specific gTTS code."""
        llm_audio_transform.source_language = "Spanish"
        df = pd.DataFrame(
            {
                "word": ["hola"],
                "sentence_1": ["Hola, mundo."],
                "sentence_2": ["Hola a todos."],
                "sentence_3": ["Gracias."],
            }
        )

        with patch.object(
            llm_audio_transform.audio_creator,
            "resolve_tts_language",
            return_value="es",
        ) as mock_resolve:
            with patch.object(
                llm_audio_transform.audio_creator, "_create_audio"
            ) as mock_create_audio:
                mock_create_audio.return_value = "/fake/audio/path.mp3"
                _ = llm_audio_transform.apply(df)

                mock_resolve.assert_called_once_with("Spanish")
                assert mock_create_audio.call_count == 3
                for call in mock_create_audio.call_args_list:
                    assert call.kwargs.get("language") == "es"
