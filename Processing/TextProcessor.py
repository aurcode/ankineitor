from dotenv import load_dotenv
import os
load_dotenv()
from tqdm import tqdm
import pandas as pd
import os
import re
from gtts import gTTS
from deep_translator import GoogleTranslator
from typing import List
import pinyin
import pinyin.cedict
from opencc import OpenCC
from datetime import datetime

#import sys
#sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../utils')))
from Utils import MongoDBClient

class AudioCreator:
    def __init__(self, folder_name: str = os.getenv('AUDIO_PATH'), language: str ='zh'):
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
            return location

        speech = gTTS(text=text, lang=self.language, slow=False)
        speech.save(location)

    def create_audios(self, texts):
        os.makedirs(self.folder_name, exist_ok=True)
        print("Creating audios")
        for key in tqdm(texts):
            path = self.folder_name + (''.join(re.findall(r'[\u4e00-\u9fffa-zA-Z0-9]+', key)))[:30]
            new_path = self._create_audio(key, path)
            self.paths.append(new_path)

class DataTransformer:
    def __init__(self, traditional = False, pinyin = True, translation = False, audio = False, time = False, save = True, test = os.getenv('DEBUG'), lan_in = 'zh-CN', lan_out = 'es'):
        self.traditional = traditional
        self.pinyin = pinyin
        self.translation = translation
        self.audio = audio
        self.time = time
        self.save = save
        self.lan_in = lan_in
        self.lan_out = lan_out

        self.columns: List[str] = ['hanzi'] + list([i for i in['pinyin', 'translation', 'audio', 'time'] if self.__dict__.get(i) is True])

        self.test = test
        if self.test:
            self.max_i = 20

        self.mongo_client = MongoDBClient()

    def transform_data(self, words):
        print("start processing")
        df = pd.DataFrame({'hanzi':words})
        df = df[df['hanzi'].notnull()]

        if self.test:
            df = df.head(self.max_i)

        if self.time:
            df['time'] = datetime.now().strftime("%d/%m/%Y")

        # This not working properly
        if self.traditional:
            self.columns.append('traditional')
            df['traditional'] = df['hanzi']
            converter = OpenCC('t2s')
            df['hanzi'] = df['hanzi'].apply(converter.convert)


        for index, row in tqdm(df.iterrows(), total=df.shape[0]):
            existing_record = self.mongo_client.find_record(row['hanzi'])
            if existing_record:
                print(row['hanzi'], 'skipped')
                for column in ['pinyin', 'translation']:
                    if existing_record[column]:
                        df.loc[index, column] = existing_record[column]
                continue

            if self.translation:
                translation_google = ''
                #if not self.test:
                translation_google = GoogleTranslator(source=self.lan_in, target=self.lan_out).translate(row['hanzi'])
                extra_mean = pinyin.cedict.translate_word(row['hanzi'])
                if extra_mean:
                    extra_mean = '. Extra mean: ' + ' | '.join(extra_mean)
                else:
                    extra_mean = ''
                df.loc[index, 'translation'] = translation_google + extra_mean

            if self.pinyin:
                df.loc[index, 'pinyin'] = pinyin.get(row['hanzi'], delimiter=" ")

            if self.save and self.pinyin and self.translation:
                self.mongo_client.insert_record(df.loc[index].to_dict())

        if self.audio:
            audioCreator = AudioCreator()
            audioCreator.create_audios(list(df['hanzi']))
            df['audio'] = audioCreator.paths

        self.mongo_client.delete_duplicates()

        print('Transformation finished')
        return df[self.columns]

    def transform_categories(self, df, category):
        #df = pd.DataFrame({'hanzi':words})
        #df = df[df['hanzi'].notnull()]

        for index, row in tqdm(df.iterrows(), total=df.shape[0]):
            self.mongo_client.add_category(row['hanzi'],category)
            df.loc[index, 'categories'] = ', '.join(self.mongo_client.get_categories(row['hanzi']))

        return df