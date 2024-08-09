#import Processing.TextExtractor
from Processing import TextExtractor
from Processing import ChineseAudioCreator
from Processing import DataTransformer
from Processing import DataIterator

uploaded_files = TextExtractor.read_files_to_uploaded(['./电路CLASSES.pdf'])
extractor = TextExtractor(uploaded_files, test=True)
extractor.extract_text()
extractor.separated_chinese_characters()
#print(extractor.phrases)
extractor.print_DF()

transformer = DataTransformer()
iterator = DataIterator()

extractor.df = transformer.transform_data(extractor.df)
extractor.print_DF()