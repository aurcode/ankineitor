import os
import re
import hashlib
from typing import List, Optional
from gtts import gTTS
from loguru import logger
from tqdm import tqdm
import pandas as pd


LANGUAGE_TO_GTTS_CODE = {
    "english": "en",
    "spanish": "es",
    "french": "fr",
    "german": "de",
    "portuguese": "pt",
    "italian": "it",
    "chinesesimplified": "zh-CN",
    "simplifiedchinese": "zh-CN",
    "chinese": "zh-CN",
    "japanese": "ja",
    "korean": "ko",
    "hindi": "hi",
    "arabic": "ar",
    "russian": "ru",
    "turkish": "tr",
    "vietnamese": "vi",
    "indonesian": "id",
}


def _normalize_language_name(value: Optional[str]) -> str:
    if not value:
        return ""
    cleaned = value.strip().lower()
    return re.sub(r"[\s_\-()]+", "", cleaned)


class AudioCreator:
    """
    Creates and saves audio files from text strings using gTTS.

    Caches files based on a hash of the text, preventing re-generation.
    """

    def __init__(self, folder_name: Optional[str] = None, language: str = "zh"):
        """
        Args:
            folder_name: Path to save audio. Defaults to AUDIO_PATH env or './audio'.
            language: Language for gTTS. Defaults to 'zh'.
        """
        # Simplified and clearer path logic
        default_path = os.getenv("AUDIO_PATH", "./audio")
        self.folder_name = folder_name if folder_name is not None else default_path
        self.language = language
        os.makedirs(self.folder_name, exist_ok=True)
        logger.info(f"AudioCreator initialized. Saving files to: {self.folder_name}")

    def resolve_tts_language(self, source_language: Optional[str] = None) -> str:
        """
        Resolve a gTTS language code from a source language label.
        Falls back to the instance default language when unknown.
        """
        normalized = _normalize_language_name(source_language)
        if normalized in LANGUAGE_TO_GTTS_CODE:
            return LANGUAGE_TO_GTTS_CODE[normalized]
        return self.language

    def _get_filename(self, text: str, language: str) -> str:
        """
        Generates a unique, safe filename using a SHA-256 hash.
        This is robust and avoids filesystem path length issues or illegal characters.
        """
        # Create a stable hash of the text
        hash_id = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return f"{hash_id[:20]}-{language}.mp3"

    def _create_audio(self, text: str, language: Optional[str] = None) -> Optional[str]:
        """
        Generates a single audio file if it doesn't already exist.

        Returns:
            The full path to the audio file, or None if creation failed.
        """
        if not text or not re.search(r"[\u4e00-\u9fffa-zA-Z0-9]", text):
            return None  # Skip empty or invalid text

        tts_language = self.resolve_tts_language(language)
        file_name = self._get_filename(text, tts_language)
        audio_file_path = os.path.join(self.folder_name, file_name)

        # Caching: If file exists, just return the path
        if os.path.exists(audio_file_path):
            return audio_file_path

        try:
            speech = gTTS(text=text, lang=tts_language, slow=False)
            speech.save(audio_file_path)
            logger.debug(f"Audio created: {audio_file_path}")
            return audio_file_path
        except Exception as e:
            logger.error(f"Error creating audio for text '{text[:20]}...': {e}")
            return None

    def create_audios_for_series(
        self, texts: pd.Series, language: Optional[str] = None
    ) -> pd.Series:
        """
        Vectorized-friendly method to generate audio for a pandas Series.

        Args:
            texts: A pandas Series containing text strings.

        Returns:
            A pandas Series containing the corresponding audio file paths.
        """
        logger.info(f"Starting audio file creation for {len(texts)} items...")

        # Use .progress_apply for a TQDM progress bar on the .apply() operation
        tqdm.pandas(desc="Generating Audio")

        # Apply the internal _create_audio method to each element in the Series
        paths = texts.progress_apply(
            lambda text: self._create_audio(text, language=language)
        )

        logger.info(f"Audio file creation complete.")
        return paths
