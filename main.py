from Processing import TextExtractor
from Processing import DataTransformer
from Processing import DataProcessor
from Ankineitor import DeckGenerator

test = True

#uploaded_files = DataProcessor.read_files_to_uploaded(['./电路CLASSES.pdf'])
#extractor = TextExtractor(uploaded_files, test=test)
#extractor.extract_text()
#extractor.separated_chinese_characters()

#transformer = DataTransformer(pinyin = True, translation = True, audio = True, time = True, test = test)
#transformer.transform_data(extractor.df['hanzi'])


#DataProcessor.print_DF(extractor.df,3)
#DataProcessor.print_DF(transformer.df)

#dataProcessor = DataProcessor()
#dataProcessor.combine_dataframes(extractor.df, transformer.df, 'hanzi')

#name_new_df = dataProcessor.save_df()
#print('name_new_df')
dataProcessor2 = DataProcessor("undefined-2024-8-18.csv")#DataProcessor(name_new_df)

DataProcessor.print_DF(dataProcessor2.df,3)

generator = DeckGenerator(
    dataProcessor2.df, 
    "tester", 
    "testomg", 
    './templates/chinese/style.css', 
    './templates/chinese/front.html', 
    './templates/chinese/front_audio.html', 
    './templates/chinese/back.html',
    "testing"
)
generator.generate_decks()

#diff_data 