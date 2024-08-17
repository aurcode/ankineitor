from tabulate import tabulate
import datetime
import pandas as pd
import os

class DataProcessor:
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

    def save_df(self, topic: str = "undefined"):
        now = datetime.datetime.now()
        name = f"{topic}-{now.year}-{now.month}-{now.day}.csv"
        self.df.head(1).to_csv(name, index=False)
        print(f"Dataframe saved in {name}.csv")
        return name

    def combine_dataframes(self, df1, df2, column):
        merged_df = pd.merge(df1, df2, on=column)
        self.df = merged_df




    def iterate_data(self, df):
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

    def diff_data(self, original_df, new_df):
        original_df = pd.read_csv('classes.csv')
        new_df = original_df.merge(new_df, left_on=['hanzi', 'mean'], right_on=['hanzi', 'mean'], how='outer', indicator=True)
        new_words = new_df.loc[new_df._merge == 'right_only'].drop(columns=['_merge'])
        new_df = new_df.drop(columns=['_merge'])
        new_df = self.iterate_data(new_df)
        new_words = self.iterate_data(new_words)
        return new_df, new_words

