from Processing import TextExtractor
from Processing import DataTransformer
from Utils import DataUtils
from Utils import stUtils
#from Ankineitor import DeckGenerator

from dotenv import load_dotenv
import os

load_dotenv()
debug = os.getenv('DEBUG')

def main():
    stu = stUtils()
    uploaded_files, file_names = stu.request_files()

    if debug:
        uploaded_files = DataUtils.read_files_to_uploaded(['C://ankineitor//电路CLASSES.pdf'])

    if uploaded_files:
        if debug:
            te = te = TextExtractor(uploaded_files)
        else:
            uploaded_file_data = {file.name: file.getvalue() for file in uploaded_files}
            te = TextExtractor(uploaded_file_data)
        te.extract_text()
        df1 = te.separated_chinese_characters()
        stu.print_DF(df1, title='Extracted Chinese Characters')

        transformer = DataTransformer(pinyin = True, translation = False, audio = False, time = True)
        df2 = transformer.transform_data(df1['hanzi'])
        stu.print_DF(df2, title='DataTransformer')

        df = DataUtils().combine_dataframes(df1, df2, 'hanzi')
        stu.print_DF(df, title='Combinator')

        df, hsk = DataUtils().filter_dataframe(df)

        stu.print_DF(hsk, title='Filtered Words')
        stu.print_DF(df, title='New DF')

    #name_new_df = DataUtils.save_df(df, '电路')
    #print(name_new_df)


#DataUtilsDF = DataUtils("history/testing.txt")
#DataUtils.print_DF(DataUtilsDF.df,3)

#generator = DeckGenerator(DataUtilsDF.df)
#generator.generate_decks()

#diff_data 

main()