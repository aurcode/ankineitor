import os
import pandas as pd
from typing import Optional
from loguru import logger
from tqdm import tqdm

from .transformations import Transformation
from .audio_creator import AudioCreator


class LLMAudioTransformation(Transformation):
    """
    Creates audio files for LLM-generated example sentences.
    Adds audio columns for each example sentence (sentence_1, sentence_2, sentence_3).
    """

    def __init__(self, audio_creator: AudioCreator):
        self.audio_creator = audio_creator
        logger.info("LLMAudioTransformation initialized")

    @property
    def column_name(self) -> str:
        """Returns the primary column name, though this creates multiple columns"""
        return "sentence_1_audio"

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Applies audio generation to LLM example sentences.
        Creates audio files for sentence_1, sentence_2, and sentence_3 columns.
        """
        logger.info("Applying LLM Audio transformation...")
        logger.info(f"Input DataFrame columns: {list(df.columns)}")
        
        # Check if required sentence columns exist
        sentence_columns = ["sentence_1", "sentence_2", "sentence_3"]
        available_sentences = [col for col in sentence_columns if col in df.columns]
        
        if not available_sentences:
            logger.warning("No LLM sentence columns found. Skipping LLM audio generation.")
            logger.warning(f"Available columns: {list(df.columns)}")
            return df

        logger.info(f"Found {len(available_sentences)} sentence columns: {available_sentences}")

        # Generate audio for each sentence column
        for sentence_col in available_sentences:
            audio_col = f"{sentence_col}_audio"
            
            if sentence_col in df.columns:
                logger.info(f"Creating audio column '{audio_col}' for {sentence_col}...")
                tqdm.pandas(desc=f"Generating audio for {sentence_col}")
                
                # Create audio files for each sentence
                df[audio_col] = df[sentence_col].progress_apply(
                    lambda sentence: self._create_sentence_audio(sentence) if pd.notna(sentence) and sentence.strip() else None
                )
                
                # Log some sample results for debugging
                sample_results = df[audio_col].dropna().head(3)
                logger.info(f"Sample audio paths for {audio_col}: {list(sample_results)}")
                logger.info(f"Audio generation complete for {sentence_col}")

        logger.info(f"Output DataFrame columns after LLM Audio: {list(df.columns)}")
        logger.info("LLM Audio transformation applied successfully")
        return df

    def _create_sentence_audio(self, sentence: str) -> Optional[str]:
        """
        Creates audio for a single sentence using the AudioCreator.
        
        Args:
            sentence: The Chinese sentence to generate audio for
            
        Returns:
            Path to the audio file, or None if creation failed
        """
        if not sentence or not sentence.strip():
            return None
            
        try:
            # Use the existing AudioCreator to generate audio
            # The AudioCreator handles caching automatically
            audio_path = self.audio_creator._create_audio(sentence.strip())
            return audio_path
        except Exception as e:
            logger.error(f"Error creating audio for sentence '{sentence[:50]}...': {e}")
            return None
