from dotenv import load_dotenv
import os

load_dotenv()

from tabulate import tabulate
import datetime
import pandas as pd
import os

class DataUtils:
    _filters = None
    df: pd.DataFrame = None

    @classmethod
    def read_files_to_uploaded(cls, file_paths):
        uploaded_files = {}
        for file_path in file_paths:
            file_name = os.path.basename(file_path)
            with open(file_path, 'rb') as file:
                file_content = file.read()
                uploaded_files[file_name] = file_content
        return uploaded_files

    @classmethod
    def get_all_categories(cls):
        from Utils import MongoDBClient
        mongo_client = MongoDBClient()
        return mongo_client.get_all_categories()

    @classmethod
    def print_DF(cls, df: pd.DataFrame, num: int = 10, head: bool=True):
        if head:
            print(tabulate(df.head(num), df.columns, tablefmt="pretty"))
        else:
            print(tabulate(df.tail(num), df.columns, tablefmt="pretty"))

    @classmethod
    def save_df(cls, df: pd.DataFrame, topic: str, path = os.getenv('DATAFRAME_SAVE_PATH')):
        now = datetime.datetime.now()
        name = f"{path}{topic}-{now.year}-{now.month}-{now.day}.csv"
        df.head(1).to_csv(name, index=False)
        print(f"Dataframe saved in {name}")
        return name

    @classmethod
    def combine_dataframes(cls, df1: pd.DataFrame, df2: pd.DataFrame, column):
        return pd.merge(df1, df2, on=column)

    @classmethod
    def filter_dataframe(cls, df, filters):
        """Filter the dataframe using the given filters dictionary."""
        df_fil = pd.DataFrame(columns=df.columns)
        df_new = df.copy()

        # Aplicar filtros en orden
        for filter_name, filter_data in filters.items():
            df_new, df_fil = cls.filter_and_save_removed(df_new, filter_data, df_fil, 'hanzi', filter_name)

        return df_new, df_fil

    @classmethod
    def fetch_hsk_files(cls):
        """Fetch HSK and other files and store them in a dictionary."""
        if cls._filters is None:
            print("Fetch HSK files")
            columns = ['hanzi', 'tradicional', 'pinyin1', 'pinyin2', 'space', 'mean']

            # Cargar archivos en un diccionario
            cls._filters = {
                'hsk1': pd.read_csv('https://raw.githubusercontent.com/aurcode/chinese-words/main/Chinese__HSK-1.txt', sep='\t', names=columns, index_col=False),
                'hsk2': pd.read_csv('https://raw.githubusercontent.com/aurcode/chinese-words/main/Chinese__HSK-2.txt', sep='\t', names=columns, index_col=False),
                'hsk3': pd.read_csv('https://raw.githubusercontent.com/aurcode/chinese-words/main/Chinese__HSK-3.txt', sep='\t', names=columns, index_col=False),
                'df_ting': pd.read_csv('https://raw.githubusercontent.com/aurcode/chinese-words/main/hsk-5-vocabulary.csv', sep=';'),
                'df_hsk5': pd.read_csv('https://raw.githubusercontent.com/aurcode/chinese-words/main/%E5%90%AC%E5%8A%9B-hsk5-vocabulary', sep=';')
            }

        return cls._filters

    @classmethod
    def read_csv(cls, path):
        df = pd.read_csv(path)
        print(df)
        df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
        df = df.drop_duplicates(subset=['hanzi'])
        df = df.sort_values(by='frequency', ascending=False)
        return df

    @classmethod
    def filter_and_save_removed(cls, df, df_final, df_saved, column_name_on, column_name_removed):
        """Helper method to filter and save removed entries."""
        filter_values = df_final['hanzi'].unique()
        filtered_df = df[df[column_name_on].isin(filter_values)].copy()
        final_df = df[~df[column_name_on].isin(filter_values)]

        filtered_df.loc[:, 'hsk'] = column_name_removed
        df_saved = df_saved.merge(filtered_df, how='outer')

        return final_df, df_saved

    @classmethod
    def combine_dataframes_sum_frequencies(cls, dfs):
        combined_df = pd.DataFrame()

        for df in dfs:
            if combined_df.empty:
                combined_df = df
            else:
                combined_df = pd.merge(combined_df, df, on=['hanzi', 'part'], how='outer', suffixes=('_left', '_right'))
                combined_df['frequency'] = combined_df[['frequency_left', 'frequency_right']].sum(axis=1, skipna=True)
                #combined_df.drop(['Unnamed:0'], axis=1)
                combined_df.reset_index(drop=True)
                combined_df = combined_df[['hanzi', 'part', 'frequency']]
        return combined_df[['hanzi', 'part', 'frequency']]
