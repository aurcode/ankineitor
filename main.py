from Processing import TextExtractor,DataTransformer
from Utils import DataUtils,stUtils, MongoDBClient
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
        df = te.separated_chinese_characters()

        return df
    return None

def filter_and_transform(df, stu, transformer):
    """Filters the DataFrame based on frequency and applies DataTransformer for pinyin, translation, audio, and time."""
    # Filter DataFrame by frequency and HSK levels
    if df is not None:
        stu.print_DF(df, title='Extracted Chinese Characters')
        if not debug:
            df, hsk = DataUtils().filter_dataframe(df)
            stu.print_DF(hsk, title='Filtered HSK Words')
            stu.print_DF(df, title='NEW Words')
            df = categories_and_transform(df, stu, transformer)
            n = stu.request_number()
        if debug:
            n = 5
        if n is not None:
            df = df[df['frequency'] > n]  # Frequency threshold

            # Apply DataTransformer for pinyin, translation, audio, and time
            _df = transformer.transform_data(df['hanzi'])

            # Combine original and transformed DataFrames
            combined_df = DataUtils().combine_dataframes(df, _df, 'hanzi')
            stu.print_DF(combined_df, title='Transformed & Combined DataFrame')

            stu.st.write(f'Your dataframe len is: {len(combined_df)}')
            return combined_df

def categories_and_transform(df, stu, dt):
    if df is not None:
        categories = stu.request_category()
        dt.transform_categories(df,categories)
        stu.print_DF(df, title='Get Categories')
        return df

def filter_by_category(df, stu):
    if df is not None:
        df = stu.filter_by_category(df)
        stu.print_DF(df, title="Filtered")
        return df

def create_deck(df, config, stu, key=''):
    if df is not None:
        if stu.st.button('Create Deck'+key):
            try:
                generator = DeckGenerator(df, config)
                filepath = generator.generate_decks()
                stu.st.write(f'Deck successfully created in {filepath}')
            except Exception as e:
                stu.st.error(f'Error creating deck: {e}')

        stu.add_separator()

def main():
    stu = stUtils()
    transformer = DataTransformer(pinyin=True, translation=True, audio=True, time=True)
    config = stu.choose_configuration_for_anki()

    config['basics']['deck_title'] = 're:零'

    if not debug:
        _df = stu.choose_dataframe()
        if _df is not None:
            create_deck(_df, config, stu)
            stu.add_separator()

    uploaded_files, file_names = stu.request_files()
    df1 = process_uploaded_files(uploaded_files, debug)
    df2 = filter_and_transform(df1, stu, transformer)

    df_f = filter_by_category(df2, stu)
    create_deck(df_f, config, stu, ' ')

main()