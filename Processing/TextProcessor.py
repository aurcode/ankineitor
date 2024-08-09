from tqdm import tqdm
import pandas as pd
import re
#from gtts import gTTS
from googletrans import GoogleTranslator
import pinyin
import math
from datetime import datetime
import os

class ChineseAudioCreator:
    def __init__(self, folder_name: str = 'audios/', language: str ='zh'):
        self.folder_name = folder_name
        self.language = language

    def _create_audio(self, text: str, path: str):
        if not text:
            return
        if not re.findall(r'[\u4e00-\u9fffa-zA-Z0-9]+', text):
            return
        speech = gTTS(text=text, lang=self.language, slow=False)
        location = path + "-" + self.language + ".mp3"
        speech.save(location)

    def create_audios(self, df, column):
        df_copy = df.to_dict()
        i = 0
        for key in df_copy['hanzi']:
            print('create audios:' + str(i) + "/" + str(len(df_copy)))
            path = self.folder_name + (''.join(re.findall(r'[\u4e00-\u9fffa-zA-Z0-9]+', df_copy['hanzi'][key])))[:30]
            self._create_audio(df_copy[column][key], path)
            df.loc[df['hanzi'] == df_copy['hanzi'][key], 'path'] = path
        return df

class DataTransformer:
    def __init__(self):
        pass

    def transform_data(self, df):
        df['created'] = datetime.now().strftime("%d/%m/%Y")
        df = df[df['hanzi'].notnull()]

        for index, row in tqdm(df.iterrows()):
            print('transformation:' + str(i) + "/" + str(len(df)))
            extra_mean = pinyin.cedict.translate_word(row['hanzi'])

            translation = GoogleTranslator(source='zh-CN', target='es').translate(row['hanzi'])
            df.loc[index, 'translation'] = translation
            df.loc[index, 'mean'] = translation
            if extra_mean:
                df.loc[index, 'mean'] = str(translation) + '. Extra mean: ' + ' | '.join(extra_mean)
            df.loc[index, 'pinyin'] = pinyin.get(row['hanzi'], delimiter=" ")

        print('Transformation finished')
        return df

class DataIterator:
    def __init__(self):
        pass

    def iterate_data(self, df):
        for index, row in df.iterrows():
            if str(row['created_y']) != 'nan':
                df.loc[index, 'created'] = row['created_y']
            if str(row['created_x']) != 'nan':
                df.loc[index, 'created'] = row['created_x']
            if str(row['pinyin_x']) != 'nan':
                df.loc[index, 'pinyin'] = row['pinyin_x']
            if str(row['part_y']) != 'nan':
                df.loc[index, 'part'] = row['part_y']
            if str(row['pinyin_y']) != 'nan':
                df.loc[index, 'pinyin'] = row['pinyin_y']
        df = df.drop(columns=['created_x', 'pinyin_x', 'created_y', 'pinyin_y'])
        return df

    def diff_data(self, original_df, new_df):
        original_df = pd.read_csv('classes.csv')
        new_df = original_df.merge(new_df, left_on=['hanzi', 'mean'], right_on=['hanzi', 'mean'], how='outer', indicator=True)
        new_words = new_df.loc[new_df._merge == 'right_only'].drop(columns=['_merge'])
        new_df = new_df.drop(columns=['_merge'])
        new_df = self.iterate_data(new_df)
        new_words = self.iterate_data(new_words)
        return new_df, new_words