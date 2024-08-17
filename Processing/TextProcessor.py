from tqdm import tqdm
import pandas as pd
import os
import re
from gtts import gTTS
from deep_translator import GoogleTranslator
from typing import List
import pinyin
import pinyin.cedict
from datetime import datetime

class AudioCreator:
    def __init__(self, folder_name: str = './audios/', language: str ='zh'):
        self.folder_name: str = folder_name
        self.language: str = language
        self.paths: List[str] = []

    def _create_audio(self, text: str, path: str):
        if not text:
            return
        if not re.findall(r'[\u4e00-\u9fffa-zA-Z0-9]+', text):
            return
        location = path + "-" + self.language + ".mp3"
        if os.path.exists(location):
            #print(f"File {location} already exists. Skipping creation.")
            return

        speech = gTTS(text=text, lang=self.language, slow=False)
        speech.save(location)

    def create_audios(self, texts):
        os.makedirs(self.folder_name, exist_ok=True)
        print("Creating audios")
        for key in tqdm(texts):
            path = self.folder_name + (''.join(re.findall(r'[\u4e00-\u9fffa-zA-Z0-9]+', key)))[:30]
            self._create_audio(key, path)
            self.paths.append(path)

class DataTransformer:
    def __init__(self, pinyin = True, translation = False, audio = False, time = False, test = False, lan_in = 'zh-CN', lan_out = 'es'):
        self.df: pd.DataFrame
        self.pinyin = pinyin
        self.translation = translation
        self.audio = audio
        self.time = time
        self.lan_in = lan_in
        self.lan_out = lan_out

        self.columns: List[str] = ['hanzi'] + list([i for i in['pinyin', 'translation', 'audio', 'time'] if self.__dict__.get(i) is True])

        self.test = test
        if self.test:
            self.max_i = 3

    def transform_data(self, words):
        df = pd.DataFrame({'hanzi':words})
        df = df[df['hanzi'].notnull()]

        if self.test:
            df = df.head(self.max_i)

        if self.time:
            df['time'] = datetime.now().strftime("%d/%m/%Y")

        print("start processing")
        for index, row in tqdm(df.iterrows(), total=df.shape[0]):
            if self.translation:
                translation_google = ''
                if not self.test:
                    translation_google = GoogleTranslator(source=self.lan_in, target=self.lan_out).translate(row['hanzi'])
                extra_mean = pinyin.cedict.translate_word(row['hanzi'])
                df.loc[index, 'translation'] = '. Extra mean: '.join(
                    [
                        translation_google,
                        ' | '.join(extra_mean)]
                )

            if self.pinyin:
                df.loc[index, 'pinyin'] = pinyin.get(row['hanzi'], delimiter=" ")

        if self.audio:
            audioCreator = AudioCreator()
            audioCreator.create_audios(list(df['hanzi']))
            df['audio'] = audioCreator.paths

        print('Transformation finished')

        self.df = df[self.columns]
