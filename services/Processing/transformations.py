import pinyin
import pinyin.cedict
import pandas as pd
from deep_translator import GoogleTranslator
from datetime import datetime
from abc import ABC, abstractmethod
from audio_creator import AudioCreator
from loguru import logger
from tqdm import tqdm

# --- Base Class for all Transformations ---


class Transformation(ABC):
    """Abstract base class for a single transformation step."""

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


class PinyinTransformation(Transformation):
    """Adds a 'pinyin' column."""

    @property
    def column_name(self) -> str:
        return "pinyin"

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        logger.info("Applying Pinyin transformation...")
        if "word" in df.columns:
            df[self.column_name] = df["word"].apply(
                lambda x: pinyin.get(x, delimiter=" ")
            )
        return df


class TranslationTransformation(Transformation):
    """Adds a 'translation' column."""

    def __init__(self, lan_in: str = "zh-CN", lan_out: str = "es"):
        self.translator = GoogleTranslator(source=lan_in, target=lan_out)
        logger.info(f"Translation_Transformation initialized: {lan_in} -> {lan_out}")

    @property
    def column_name(self) -> str:
        return "translation"

    def _translate_with_extras(self, word: str) -> str:
        """Helper to combine Google Translate with CEDICT."""
        try:
            translation = self.translator.translate(word)
            extra_meanings = pinyin.cedict.translate_word(word)

            if extra_meanings:
                # Add extra meanings, ensuring no duplicates
                extras = " | ".join(set(extra_meanings))
                return f"{translation}. Extras: {extras}"
            return translation
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

    def __init__(self, audio_creator: AudioCreator):
        self.audio_creator = audio_creator

    @property
    def column_name(self) -> str:
        return "audio"

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        logger.info("Applying Audio transformation...")
        if "word" in df.columns:
            # Pass the whole Series to the audio creator's optimized method
            df[self.column_name] = self.audio_creator.create_audios_for_series(
                df["word"]
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
