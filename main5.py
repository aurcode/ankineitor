from Processing import DataTransformer
from Utils import DataUtils,stUtils
from Ankineitor import DeckGenerator
from dotenv import load_dotenv
import os

load_dotenv()
debug = os.getenv('DEBUG')

def filters_df(df, stu, transformer):
    """Filters the DataFrame based on frequency and applies DataTransformer for pinyin, translation, audio, and time."""
    # Filter DataFrame by frequency and HSK levels
    if df is not None:
        df_new = transformer.transform_categories(df)
        stu.print_DF(df_new, title='Extracted Chinese Characters')
        df_filtered = stu.filter_by_category(df_new[df_new['frequency']>stu.request_number()])
        if df_filtered is not None:
                return df_filtered
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
        #combined_df.to_csv('final.csv')

def create_deck(config, stu, key='', df_name='final.csv'):
    if stu.create_button('Create Deck'+key):
            if 'deck_created' not in stu.st.session_state:
                stu.st.session_state['deck_created'] = False
            if not stu.st.session_state['deck_created']:
                generator = DeckGenerator(df_name, config)
                filepath = generator.generate_decks()
                stu.st.write(f'Deck successfully created in {filepath}')
                stu.st.session_state['deck_created'] = True
                return filepath

    return None

def main():
    stu = stUtils()
    transformer = DataTransformer(pinyin=True, translation=True, audio=True, time=True)

    df1 = stu.choose_dataframes()
    df2 = filters_df(df1, stu, transformer)
    transformation_df(df2, stu, transformer)
    stu.add_separator()

    config = stu.choose_configuration_for_anki()
    config['basics']['deck_title'] = 'CLASSES_VOCABULARY'
    config['basics']['filename'] = config['basics']['deck_title'] + '.apkg'
    create_deck(config, stu)

main()