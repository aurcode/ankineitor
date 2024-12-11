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




gg = pd.DataFrame({"hanzi": ['然后','','你好']}).hanzi


cwp = ChineseWordProcessor()
print(cwp.process_words(gg))


#print(dt.transform_data(gg))

