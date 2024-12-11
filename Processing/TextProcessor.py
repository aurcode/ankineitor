from deep_translator import GoogleTranslator
from gtts import gTTS
from datetime import datetime
from dotenv import load_dotenv
from typing import List, Optional
from tqdm import tqdm
import pandas as pd
import numpy as np
import os
import re
import pinyin
import pinyin.cedict
#from opencc import OpenCC

from Utils import MongoDBClient
load_dotenv()

class AudioCreator:
    def __init__(self, folder_name: str = None, language: str = 'zh'):
        """
        AudioCreator class to generate audio files from text.

        Args:
            folder_name (str): Path to the folder where audio files will be saved. Defaults to `AUDIO_PATH` environment variable.
            language (str): Language for text-to-speech. Defaults to 'zh' (Chinese).
        """
        self.folder_name: str = '/opt/audio/' if os.getenv('DOCKER') else os.getenv('AUDIO_PATH')
        self.language: str = language
        self.paths: List[str] = []

    def _sanitize_text(self, text: str) -> str:
        """
        Sanitize input text to create a valid filename.

        Args:
            text (str): Input text to sanitize.

        Returns:
            str: Sanitized text.
        """
        return ''.join(re.findall(r'[\u4e00-\u9fffa-zA-Z0-9]+', text))[:30]

    def _create_audio(self, text: str, file_path: str) -> str:
        """
        Generate an audio file for the given text if it doesn't already exist.

        Args:
            text (str): Text to convert to speech.
            file_path (str): Path where the audio file will be saved.

        Returns:
            str: Path of the created or existing audio file.
        """
        if not text:
            return None

        if not re.search(r'[\u4e00-\u9fffa-zA-Z0-9]', text):
            return None

        audio_file = f"{file_path}-{self.language}.mp3"
        if os.path.exists(audio_file):
            return audio_file

        try:
            speech = gTTS(text=text, lang=self.language, slow=False)
            speech.save(audio_file)
            return audio_file
        except Exception as e:
            print(f"Error creating audio for text '{text}': {e}")
            return None

    def create_audios(self, texts: List[str]) -> List[str]:
        """
        Generate audio files for a list of texts.

        Args:
            texts (List[str]): List of texts to convert to speech.

        Returns:
            List[str]: List of paths to the generated audio files.
        """
        os.makedirs(self.folder_name, exist_ok=True)
        print("Creating audio files...")

        for text in tqdm(texts, desc="Audio creation"):
            sanitized_name = self._sanitize_text(text)
            file_path = os.path.join(self.folder_name, sanitized_name)
            audio_file = self._create_audio(text, file_path)
            if audio_file:
                self.paths.append(audio_file)

        return self.paths

class DataTransformer:
    def __init__(
            self,
            traditional_enabled: bool = False,
            pinyin_enabled: bool = False,
            translation_enabled: bool = False,
            audio_enabled: bool = False,
            timestamp_enabled: bool = False,
            save_enabled: bool = True,
            dev_enabled: bool = os.getenv('DEBUG'),
            lan_in: str = 'zh-CN',
            lan_out: str = 'es',
            mongo_client: MongoDBClient = MongoDBClient(),
            audio_creator: AudioCreator = AudioCreator()
        ):
        """
        DataTransformer class for processing Chinese words.

        Args:
            traditional_enabled (bool): Enable/Disable traditional Chinese conversion.
            pinyin_enabled (bool): Enable/Disable pinyin generation.
            translation_enabled (bool): Enable/Disable translations.
            audio_enabled (bool): Enable/Disable audio creation.
            timestamp_enabled (bool): Add timestamps to processed data.
            save_enabled (bool): Save transformed data to DB.
            dev_enabled (bool): Enable test mode with limited data.
            lan_in (str): Input language for translation.
            lan_out (str): Output language for translation.
            mongo_client: MongoDB client for database operations.
            audio_creator: AudioCreator instance for generating audio files.
        """
        self.traditional_enabled = traditional_enabled
        self.pinyin_enabled = pinyin_enabled
        self.translation_enabled = translation_enabled
        self.audio_enabled = audio_enabled
        self.timestamp_enabled = timestamp_enabled
        self.save_enabled = save_enabled
        self.lan_in = lan_in
        self.lan_out = lan_out

        self.columns = self._determine_columns()
        self.dev_enabled = dev_enabled
        self.max_records = 20 if self.dev_enabled else None
        self.mongo_client = mongo_client
        self.audio_creator = audio_creator


    def _determine_columns(self) -> List[str]:
        """
        Determine columns based on enabled options.
        """
        base_columns = ['hanzi']
        optional_columns = [
            column for column, enabled in {
                'pinyin': self.pinyin_enabled,
                'translation': self.translation_enabled,
                'audio': self.audio_enabled,
                'timestamp': self.timestamp_enabled
            }.items() if enabled
        ]
        return base_columns + optional_columns

    def _add_timestamp(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add timestamp to the DataFrame if enabled.
        """
        if self.timestamp_enabled:
            df['timestamp'] = datetime.now().strftime("%d/%m/%Y")
        return df

    def _convert_to_traditional(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Convert simplified Chinese characters to traditional.
        """
        if self.traditional_enabled:
            self.columns.append('traditional')
            df['traditional'] = df['hanzi']
            converter = OpenCC('t2s')
            df['hanzi'] = df['hanzi'].apply(converter.convert)
        return df

    def _generate_audio(self, df: pd.DataFrame) -> pd.DataFrame:
        if self.audio_enabled and self.audio_creator:
            self.audio_creator.create_audios(list(df['hanzi']))
            df['audio'] = self.audio_creator.paths
        return df

    def _translate_word(self, word: str) -> str:
        """
        Translate a word using Google Translator and include extra meanings.
        """
        translator = GoogleTranslator(source=self.lan_in, target=self.lan_out)
        translation = translator.translate(word, src=self.lan_in, dest=self.lan_out)
        extra_meanings = pinyin.cedict.translate_word(word)
        if extra_meanings:
            translation += f". Extra meanings: {' | '.join(extra_meanings)}"
        return translation

    def _transform_row(self, row: pd.Series) -> pd.Series:
        """
        Transform a single row of data.
        """
        print("Transforming with translation and pinyin")
        if self.translation_enabled:
            row['translation'] = self._translate_word(row['hanzi'])

        if self.pinyin_enabled:
            row['pinyin'] = pinyin.get(row['hanzi'], delimiter=" ")

        if self.save_enabled and self.pinyin_enabled and self.translation_enabled:
            self.mongo_client.insert_record(row.to_dict(), ['pinyin', 'translation', 'timestamp'])

        return row

    def transform_data(self, words: List[str]) -> pd.DataFrame:
        """
        Transform a list of Chinese words.
        """
        print("Starting data transformation...")
        df = pd.DataFrame({'hanzi': words}).replace('', np.nan).dropna()

        if self.pinyin_enabled:
            df['pinyin'] = None
        if self.translation_enabled:
            df['translation'] = None
        if self.timestamp_enabled:
            df['timestamp'] = None
        if self.audio_enabled:
            df['audio'] = None

        if self.dev_enabled:
            df = df.head(self.max_records)

        df = self._add_timestamp(df)
        df = self._convert_to_traditional(df)


        for index, row in tqdm(df.iterrows(), total=df.shape[0]):
            existing_record = self.mongo_client.find_record(row['hanzi'])
            if existing_record:
                for column in ['pinyin', 'translation']:
                    row[column] = existing_record.get(column, row.get(column))
                if row['pinyin'] and row['translation']:
                    df.loc[index] = row
                    continue

            row = self._transform_row(row)
            df.loc[index] = row

        df = self._generate_audio(df)
        self.mongo_client.delete_duplicates()

        print("Data transformation complete.")
        return df[self.columns]

    def transform_categories(self, df: pd.DataFrame, category: Optional[str] = None) -> pd.DataFrame:
        """
        Transform and add categories to the DataFrame.
    """
        for index, row in tqdm(df.iterrows(), total=df.shape[0]):
            if category:
                self.mongo_client.add_category(row['hanzi'], category)
            categories = self.mongo_client.get_categories(row['hanzi'])
            df.loc[index, 'categories'] = ', '.join(categories)
        return df.reset_index(drop=True)