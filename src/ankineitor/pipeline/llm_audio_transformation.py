import pandas as pd
from typing import Optional
from loguru import logger
from tqdm import tqdm
import re
import random

from .transformations import Transformation
from .audio_creator import AudioCreator
from .llm_profiles import DEFAULT_LLM_PROFILE_ID, get_llm_profile


class LLMAudioTransformation(Transformation):
    """
    Creates audio files for LLM-generated example sentences.
    Adds audio columns for each detected sentence column (sentence_1..sentence_N).
    """

    pipeline_stage = "llm"
    required_input_columns = ("sentence_1",)

    def __init__(
        self,
        audio_creator: AudioCreator,
        source_language: str = "Chinese (Simplified)",
        profile_id: str = DEFAULT_LLM_PROFILE_ID,
    ):
        self.audio_creator = audio_creator
        self.source_language = source_language
        self.profile_id = profile_id
        logger.info("LLMAudioTransformation initialized")

    def _resolve_profile_voice(self) -> Optional[str]:
        profile = get_llm_profile(self.profile_id)
        if profile.tts_voice_pool:
            selected = random.choice(profile.tts_voice_pool)
            logger.info(
                "LLM sentence audio random voice '{}' selected from profile '{}' pool of {} voice(s).",
                selected,
                profile.profile_id,
                len(profile.tts_voice_pool),
            )
            return selected

        selected = (profile.default_tts_voice_id or "").strip()
        if selected:
            logger.info(
                "LLM sentence audio voice resolved to '{}' for profile '{}'.",
                selected,
                profile.profile_id,
            )
            return selected

        return None

    def _has_text(self, value: object) -> bool:
        if value is None:
            return False
        if pd.isna(value):
            return False
        return bool(str(value).strip())

    def _resolve_sentence_source_series(
        self,
        df: pd.DataFrame,
        sentence_col: str,
        tts_col: str,
    ) -> pd.Series:
        """Resolve per-row source text prioritizing sentence-specific tts_clean values."""
        if tts_col in df.columns and sentence_col in df.columns:
            return df.apply(
                lambda row: row[tts_col]
                if self._has_text(row[tts_col])
                else row[sentence_col],
                axis=1,
            )
        if tts_col in df.columns:
            return df[tts_col]
        return df[sentence_col]

    @property
    def column_name(self) -> str:
        """Returns the primary column name, though this creates multiple columns"""
        return "sentence_1_audio"

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Applies audio generation to LLM example sentences.
        Creates audio files for all sentence_{n} columns found in the DataFrame.
        """
        logger.info("Applying LLM Audio transformation...")
        logger.info(f"Input DataFrame columns: {list(df.columns)}")
        
        # Dynamically detect sentence groups:
        # - sentence_N
        # - sentence_N_tts_clean (fallback when highlighted sentence is absent)
        sentence_pattern = re.compile(r"^sentence_(\d+)$")
        tts_clean_pattern = re.compile(r"^sentence_(\d+)_tts_clean$")
        sentence_indexes = set()
        for column in df.columns:
            name = str(column)
            sentence_match = sentence_pattern.match(name)
            if sentence_match:
                sentence_indexes.add(int(sentence_match.group(1)))
                continue
            tts_match = tts_clean_pattern.match(name)
            if tts_match:
                sentence_indexes.add(int(tts_match.group(1)))
        available_sentences = [f"sentence_{idx}" for idx in sorted(sentence_indexes)]
        
        if not available_sentences:
            logger.warning("No LLM sentence columns found. Skipping LLM audio generation.")
            logger.warning(f"Available columns: {list(df.columns)}")
            return df

        logger.info(f"Found {len(available_sentences)} sentence columns: {available_sentences}")
        tts_language = self.audio_creator.resolve_tts_language(self.source_language)
        logger.info(
            f"LLM sentence audio language resolved to '{tts_language}' "
            f"from source '{self.source_language}'."
        )

        profile_voice = self._resolve_profile_voice()
        previous_voice = self.audio_creator.minimax_voice_id
        fallback_voice_id: Optional[str] = None
        if profile_voice:
            self.audio_creator.minimax_voice_id = profile_voice
            if previous_voice and previous_voice != profile_voice:
                fallback_voice_id = previous_voice

        try:
            # Generate audio for each sentence column
            for sentence_col in available_sentences:
                audio_col = f"{sentence_col}_audio"
                tts_col = f"{sentence_col}_tts_clean"

                if sentence_col in df.columns or tts_col in df.columns:
                    logger.info(f"Creating audio column '{audio_col}' for {sentence_col}...")
                    tqdm.pandas(desc=f"Generating audio for {sentence_col}")

                    source_series = self._resolve_sentence_source_series(
                        df=df,
                        sentence_col=sentence_col,
                        tts_col=tts_col,
                    )
                    if audio_col in df.columns:
                        output_series = df[audio_col].copy()
                    else:
                        output_series = pd.Series(index=df.index, dtype=object)

                    missing_mask = ~output_series.apply(self._has_text)
                    if missing_mask.any():
                        generated_series = source_series[missing_mask].progress_apply(
                            lambda sentence: self._create_sentence_audio_with_voice_fallback(
                                sentence,
                                language=tts_language,
                                fallback_voice_id=fallback_voice_id,
                            )
                            if self._has_text(sentence)
                            else None
                        )
                        output_series.loc[missing_mask] = generated_series
                    else:
                        logger.info(
                            f"Skipping generation for '{audio_col}': existing audio already present."
                        )

                    df[audio_col] = output_series

                    # Log some sample results for debugging
                    sample_results = df[audio_col].dropna().head(3)
                    logger.info(f"Sample audio paths for {audio_col}: {list(sample_results)}")
                    logger.info(f"Audio generation complete for {sentence_col}")
        finally:
            self.audio_creator.minimax_voice_id = previous_voice

        logger.info(f"Output DataFrame columns after LLM Audio: {list(df.columns)}")
        logger.info("LLM Audio transformation applied successfully")
        return df

    def _create_sentence_audio_with_voice_fallback(
        self,
        sentence: str,
        language: Optional[str] = None,
        fallback_voice_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Try sentence audio with the active profile voice, then retry once with a fallback voice.
        """
        current_voice = str(self.audio_creator.minimax_voice_id or "").strip()
        audio_path = self._create_sentence_audio(sentence, language=language)
        if audio_path or not fallback_voice_id:
            return audio_path

        fallback = str(fallback_voice_id).strip()
        if not fallback or fallback == current_voice:
            return audio_path

        logger.warning(
            "LLM sentence audio retry with fallback voice '{}' after failure with profile voice '{}'.",
            fallback,
            current_voice,
        )
        self.audio_creator.minimax_voice_id = fallback
        try:
            return self._create_sentence_audio(sentence, language=language)
        finally:
            self.audio_creator.minimax_voice_id = current_voice

    def _create_sentence_audio(
        self, sentence: str, language: Optional[str] = None
    ) -> Optional[str]:
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
            audio_path = self.audio_creator._create_audio(
                sentence.strip(), language=language
            )
            return audio_path
        except Exception as e:
            logger.error(f"Error creating audio for sentence '{sentence[:50]}...': {e}")
            return None
