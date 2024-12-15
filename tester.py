from Processing import TextExtractor,DataTransformer,ChineseWordProcessor
from Utils import DataUtils,stUtils
from Ankineitor import DeckGenerator
from dotenv import load_dotenv
import pandas as pd
import os

load_dotenv()
debug = os.getenv('DEBUG')

dt = DataTransformer(
            traditional_enabled = False,
            pinyin_enabled = True,
            translation_enabled = True,
            audio_enabled = True,
            timestamp_enabled = True,
            save_enabled = True,
            dev_enabled = True,
        )




gg = pd.DataFrame({"hanzi": ['的','啥意思','明白了吗']}).hanzi

dt.transform_data(gg)

cwp = ChineseWordProcessor()
cwp.process_words(gg)

#cwp.process_words(gg)

#print(cwp.process_words(gg).columns)

#print(dt.transform_data(gg))

