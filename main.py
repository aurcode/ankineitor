#import Processingp.TextExtractor
from Processing import TextExtractor
from Processing import DataTransformer

uploaded_files = TextExtractor.read_files_to_uploaded(['./电路CLASSES.pdf'])
extractor = TextExtractor(uploaded_files, test=True)
extractor.extract_text()
extractor.separated_chinese_characters()

transformer = DataTransformer(pinyin = True, translation = True, audio = True, time = True, test = True)
transformer.transform_data(extractor.df['hanzi'])

###iterator = DataIterator()
extractor.print_DF(3)

print(transformer.df)