from dotenv import load_dotenv
import os

load_dotenv()

from tabulate import tabulate
import datetime
import pandas as pd
import os

class DataUtils:
    def __init__(self, path: str = ''):
        self.df: pd.DataFrame
        if path != '':
            self.df = pd.read_csv(path)

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
    def filter_and_save_removed(cls, df, df_final, df_saved, column_name_on, column_name_removed):
        filter_values = df_final['hanzi'].unique()
        filtered_df = df[df[column_name_on].isin(filter_values)]
        final_df = df[~df[column_name_on].isin(filter_values)]

        filtered_df['hsk'] = column_name_removed
        df_saved = df_saved.merge(filtered_df,  how='outer')

        return final_df, df_saved

    @classmethod
    def filter_dataframe(cls, df):
        columns=['hanzi', 'tradicional','pinyin1','pinyin2','space','mean']
        hsk1=pd.read_csv('https://raw.githubusercontent.com/aurcode/chinese-words/main/Chinese__HSK-1.txt',sep='\t',names=columns, index_col=False)
        hsk2=pd.read_csv('https://raw.githubusercontent.com/aurcode/chinese-words/main/Chinese__HSK-2.txt',sep='\t',names=columns, index_col=False)
        hsk3=pd.read_csv('https://raw.githubusercontent.com/aurcode/chinese-words/main/Chinese__HSK-3.txt',sep='\t',names=columns, index_col=False)

        df_ting=pd.read_csv('https://raw.githubusercontent.com/aurcode/chinese-words/main/hsk-5-vocabulary.csv',sep=';')
        df_hsk5=pd.read_csv('https://raw.githubusercontent.com/aurcode/chinese-words/main/%E5%90%AC%E5%8A%9B-hsk5-vocabulary',sep=';')

        df_fil = pd.DataFrame(columns=df.columns)

        df_new, df_fil = cls.filter_and_save_removed(df, hsk1, df_fil, 'hanzi', 'hsk1')
        df_new, df_fil = cls.filter_and_save_removed(df_new, hsk2, df_fil, 'hanzi', 'hsk2')
        df_new, df_fil = cls.filter_and_save_removed(df_new, hsk3, df_fil, 'hanzi', 'hsk3')
        #df_new, df_fil = filter_and_save_removed(df_new, hsk4, df_fil, 'hanzi', 'hsk4')
        #df_new, df_fil = filter_and_save_removed(df_new, hsk5, df_fil, 'hanzi', 'hsk5')

        df_new, df_fil = cls.filter_and_save_removed(df_new, df_ting, df_fil, 'hanzi', 'df_ting')
        df_new, df_fil = cls.filter_and_save_removed(df_new, df_hsk5, df_fil, 'hanzi', 'df_hsk5')

        return df_new, df_fil

    @classmethod
    def iterate_data(cls, df):
        for index, row in df.iterrows():
            if str(row['created_y']) != 'nan':
                df.loc[index, 'created'] = row['created_y']
            if str(row['created_x']) != 'nan':
                df.loc[index, 'created'] = row['created_x']
            if str(row['pinyin_x']) != 'nan':
                df.loc[index, 'pinyin'] = row['pinyin_x']
            if str(row['part_y']) != 'nan':
                df.loc[index, 'part'] = row['part_y']
            if str(row['pinyin_y']) != 'nan':
                df.loc[index, 'pinyin'] = row['pinyin_y']
        df = df.drop(columns=['created_x', 'pinyin_x', 'created_y', 'pinyin_y'])
        return df

    @classmethod
    def diff_data(cls, original_df, new_df):
        original_df = pd.read_csv('classes.csv')
        new_df = original_df.merge(new_df, left_on=['hanzi', 'mean'], right_on=['hanzi', 'mean'], how='outer', indicator=True)
        new_words = new_df.loc[new_df._merge == 'right_only'].drop(columns=['_merge'])
        new_df = new_df.drop(columns=['_merge'])
        new_df = self.iterate_data(new_df)
        new_words = self.iterate_data(new_words)
        return new_df, new_words

