from Processing import TextExtractor
from Processing import DataTransformer
from Utils import DataUtils
from Utils import stUtils
from Ankineitor import DeckGenerator
from dotenv import load_dotenv
import os

load_dotenv()
debug = os.getenv('DEBUG')

def process_uploaded_files(uploaded_files, debug=False):
    """Processes uploaded files by extracting Chinese characters, applying transformations, and returning combined DataFrame."""
    # Handle debug mode with pre-loaded files
    if debug:
        uploaded_files = DataUtils.read_files_to_uploaded(['C://ankineitor//电路CLASSES.pdf'])

    if uploaded_files:
        # Text extraction
        file_data = {file.name: file.getvalue() for file in uploaded_files} if not debug else uploaded_files
        te = TextExtractor(file_data)
        te.extract_text()
        df1 = te.separated_chinese_characters()

        return df1
    return None

def filter_and_transform(df1, stu):
    """Filters the DataFrame based on frequency and applies DataTransformer for pinyin, translation, audio, and time."""
    # Filter DataFrame by frequency and HSK levels
    stu.print_DF(df1, title='Extracted Chinese Characters')
    if not debug:
        df1, hsk = DataUtils().filter_dataframe(df1)
        stu.print_DF(hsk, title='Filtered HSK Words')
        stu.print_DF(df1, title='NEW Words')
        n = stu.request_number()
    if debug:
        n = 5
    if n is not None:
        df1 = df1[df1['frequency'] > n]  # Frequency threshold

        # Apply DataTransformer for pinyin, translation, audio, and time
        transformer = DataTransformer(pinyin=True, translation=True, audio=True, time=True)
        df2 = transformer.transform_data(df1['hanzi'])

        # Combine original and transformed DataFrames
        combined_df = DataUtils().combine_dataframes(df1, df2, 'hanzi')
        stu.print_DF(combined_df, title='Transformed & Combined DataFrame')

        stu.st.write(f'Your dataframe len is: {len(combined_df)}')
        return combined_df

def create_deck(df, config, stu, key=''):
    if stu.st.button('Create Deck'+key):
        try:
            generator = DeckGenerator(df, config)
            filepath = generator.generate_decks()
            stu.st.write(f'Deck successfully created in {filepath}')
        except Exception as e:
            stu.st.error(f'Error creating deck: {e}')

def main():
    stu = stUtils()
    config = stu.choose_configuration_for_anki()
    if not debug:
        _df = stu.choose_dataframe()
        if _df is not None:
            create_deck(_df, config, stu)
            stu.add_separator()

    uploaded_files, file_names = stu.request_files()
    df1 = process_uploaded_files(uploaded_files, debug)

    if df1 is not None:
        df = filter_and_transform(df1, stu)
        if df is not None:
            create_deck(df, config, stu, ' ')
            stu.add_separator()

main()