from Processing import DataTransformer
from Utils import DataUtils,stUtils
from Ankineitor import DeckGenerator
from Processing import ChineseWordProcessor 
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
        df_masked = filter_by_category(df_new, stu)
        if df_masked is not None:
            n = stu.request_number()
            if n is not None and df_masked is not None:
                df_f = df_masked[df_masked['frequency']>=n]
                if df_f is not None:
                    return df_f
    return None

def filter_by_category(df, stu):
    if df is not None:
        _df = stu.filter_by_category(df)
        return _df
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
        combined_df.to_csv('final.csv')

def create_deck(config, stu, key='', df_name='final_with_ai.csv'):
    if stu.create_button('Create Deck'+key):
            if 'deck_created' not in stu.st.session_state:
                stu.st.session_state['deck_created'] = False
            if not stu.st.session_state['deck_created']:
                df = DataUtils.read_csv(df_name)
                dt = DataTransformer(audio=True)
                df['audio'] = dt.transform_data(df['hanzi'])['audio']
                generator = DeckGenerator(df, config)
                filepath = generator.generate_decks()
                stu.st.write(f'Deck successfully created in {filepath}')
                stu.st.session_state['deck_created'] = True
                return filepath

    return None

def main():
    stu = stUtils()
    dt = DataTransformer(pinyin=True, translation=True, audio=True, time=True)
    cwp = ChineseWordProcessor()

    df1 = stu.choose_dataframes()
    df2 = filters_df(df1, stu, dt)
    transformation_df(df2, stu, dt)
    stu.add_separator()

    if stu.create_button('Improve with AI'):
        df = DataUtils.read_csv('./final.csv')
        stu.print_DF(df)
        df_new = cwp.process_words(list(df['hanzi']), dict(df['translation']))
        stu.print_DF(df_new)
        df_final = DataUtils.combine_dataframes(df, df_new, 'hanzi')
        for idx, row in df_final.iterrows():
            try:
                df_final.at[idx, 'meaning_extra'] = " "
                means = row['translation'].split('Extra mean: ')
                if len(means) == 2:
                    df_final.at[idx, 'meaning_extra'] = means[-1].strip()
            except ValueError:
                df_final.at[idx, 'meaning_extra'] = " "
        stu.print_DF(df_final)
        df_final.to_csv('./final_with_ai.csv', index=False)

    stu.add_separator()

    config = stu.choose_configuration_for_anki()
    print(config['basics']['filename'])
    create_deck(config, stu)

main()