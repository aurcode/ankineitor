from Processing import TextExtractor,DataTransformer
from Utils import DataUtils,stUtils
from Ankineitor import DeckGenerator
from dotenv import load_dotenv
import os

load_dotenv()
debug = os.getenv('DEBUG')
#filters = None
filters = DataUtils.fetch_hsk_files()

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

def filters_df(df, stu, transformer, filters = None):
    """Filters the DataFrame based on frequency and applies DataTransformer for pinyin, translation, audio, and time."""
    # Filter DataFrame by frequency and HSK levels
    if df is not None:
        if debug:
            #n = 5
            df_new = df
            stu.print_DF(df_new, title='Extracted Chinese Characters')
            n = stu.request_number()
        if not debug:
            if filters is None:
                df_filtered, hsk = DataUtils.filter_dataframe(df, filters)
                stu.print_DF(hsk, title='Filtered HSK Words')
                stu.print_DF(df_filtered, title='NEW Words')
            if df_filtered is not None:
                df_new = categories_and_transform(df_filtered, stu, transformer)
            n = stu.request_number()

        if n is not None and df_new is not None:
            df_f = df_new[df_new['frequency']>n]
            if df_f is not None:
                return df_f
    return None

def transformation_df(df, stu, transformer):
    if df is not None:
        new_df = df.copy()
        # Apply DataTransformer for pinyin, translation, audio, and time
        _df = transformer.transform_data(df['hanzi'])
        # Combine original and transformed DataFrames
        combined_df = DataUtils().combine_dataframes(new_df, _df, 'hanzi')
        stu.print_DF(combined_df, title='Transformed & Combined DataFrame')
        stu.st.write(f'Your dataframe len is: {len(combined_df)}')
        return combined_df

def categories_and_transform(df, stu, dt):
    if df is not None:
        categories = stu.request_category()
        _df = dt.transform_categories(df,categories)
        stu.print_DF(_df, title='Get Categories')
        return _df
    return None

def filter_by_category(df, stu):
    if df is not None:
        _df = stu.filter_by_category(df)
        return _df
    return None

def create_deck(df, config, stu, key=''):
    if df is not None:
        if stu.create_button('Create Deck'+key):
            try:
                if 'deck_created' not in st.session_state:
                    stu.st.session_state['deck_created'] = False

                if not stu.st.session_state['deck_created']:
                    generator = DeckGenerator(df, config)
                    filepath = generator.generate_decks()
                    stu.st.write(f'Deck successfully created in {filepath}')
                    stu.st.session_state['deck_created'] = True
                    return filepath
            except Exception as e:
                stu.st.error(f'Error creating deck: {e}')
    return None

def main():
    stu = stUtils()
    transformer = DataTransformer(pinyin=True, translation=True, audio=True, time=True)
    uploaded_files, file_names = stu.request_files()
    df1 = process_uploaded_files(uploaded_files, debug)
    df2 = filters_df(df1, stu, transformer, filters)
    df3 = transformation_df(df2, stu, transformer)

main()