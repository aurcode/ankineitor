import pinyin
import pinyin.cedict
import pandas as pd
from deep_translator import GoogleTranslator
from datetime import datetime
from abc import ABC, abstractmethod
import re
from .audio_creator import AudioCreator
from loguru import logger
from tqdm import tqdm

# --- Base Class for all Transformations ---


class Transformation(ABC):
    """Abstract base class for a single transformation step."""

    # Metadata used by orchestration layers to group/schedule transforms.
    pipeline_stage: str = "main"
    required_input_columns: tuple[str, ...] = ()
    llm_parallel_mode: str = "sequential"

    @property
    def column_name(self) -> str:
        """The name of the column this transformation creates/modifies."""
        raise NotImplementedError

    @abstractmethod
    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Applies the transformation to a DataFrame.
        Must operate on and return a DataFrame.
        """
        pass


# --- Concrete Transformation Classes ---


# Basic Han character detector for pinyin gating.
_CHINESE_CHAR_PATTERN = re.compile(r"[\u4e00-\u9fff]")


def _contains_chinese_characters(value: str) -> bool:
    return bool(_CHINESE_CHAR_PATTERN.search(value or ""))


def _normalize_language_name(language: str) -> str:
    if not language:
        return ""
    normalized = str(language).strip().lower()
    normalized = re.sub(r"[\s_\-()]+", "", normalized)
    return normalized


def _language_is_chinese(language: str) -> bool:
    return _normalize_language_name(language) in {
        "chinesesimplified",
        "simplifiedchinese",
        "chinese",
        "zh",
        "zhcn",
        "chinesetraditional",
        "traditionalchinese",
    }


class PinyinTransformation(Transformation):
    """Adds a 'pinyin' column."""

    def __init__(self, source_language: str = "Chinese (Simplified)"):
        self.source_language = source_language

    @property
    def column_name(self) -> str:
        return "pinyin"

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        logger.info("Applying Pinyin transformation...")
        source_is_chinese = _language_is_chinese(self.source_language)
        if "word" in df.columns:
            if not source_is_chinese:
                logger.info(
                    f"Skipping pinyin generation for non-Chinese source language: {self.source_language}"
                )
                df[self.column_name] = None
                return df
            df[self.column_name] = df["word"].apply(
                lambda x: (
                    pinyin.get(str(x), delimiter=" ")
                    if _contains_chinese_characters(str(x))
                    else None
                )
            )
        return df


class TranslationTransformation(Transformation):
    """Adds a 'translation' column."""

    def __init__(self, lan_in: str = "zh-CN", lan_out: str = "en"):
        self.translator = GoogleTranslator(source=lan_in, target=lan_out)
        logger.info(f"Translation_Transformation initialized: {lan_in} -> {lan_out}")

    @property
    def column_name(self) -> str:
        return "translation"

    def _translate_with_extras(self, word: str) -> str:
        """Helper to combine Google Translate with CEDICT."""
        try:
            extra_meanings = pinyin.cedict.translate_word(word)

            if extra_meanings:
                # Add extra meanings, ensuring no duplicates
                return " | ".join(set(extra_meanings))
            return self.translator.translate(word)
        except Exception as e:
            logger.error(f"Error translating word '{word}': {e}")
            return None

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        logger.info("Applying Translation transformation...")
        if "word" in df.columns:
            tqdm.pandas(desc="Translating")
            df[self.column_name] = df["word"].progress_apply(
                self._translate_with_extras
            )
        return df


class AudioTransformation(Transformation):
    """Adds an 'audio' column using AudioCreator."""

    def __init__(
        self,
        audio_creator: AudioCreator,
        source_language: str = "Chinese (Simplified)",
    ):
        self.audio_creator = audio_creator
        self.source_language = source_language

    @property
    def column_name(self) -> str:
        return "audio"

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        logger.info("Applying Audio transformation...")
        if "word" in df.columns:
            tts_language = self.audio_creator.resolve_tts_language(self.source_language)
            # Pass the whole Series to the audio creator's optimized method
            df[self.column_name] = self.audio_creator.create_audios_for_series(
                df["word"], language=tts_language
            )
        return df


class TimestampTransformation(Transformation):
    """Adds a 'timestamp' column."""

    @property
    def column_name(self) -> str:
        return "timestamp"

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        logger.info("Applying Timestamp transformation...")
        df[self.column_name] = datetime.now().strftime("%d/%m/%Y")
        return df
