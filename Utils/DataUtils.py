import os
import datetime
import pandas as pd
from typing import List
from dotenv import load_dotenv
from tabulate import tabulate
from loguru import logger

# Load environment variables
load_dotenv()

class FileHandler:
    """Handles file operations such as reading and loading files."""

    @staticmethod
    def read_file(file_path: str) -> bytes:
        """Read a file and return its content as bytes."""
        try:
            with open(file_path, 'rb') as file:
                file_content = file.read()
            logger.info(f"Successfully read file: {file_path}")
            return file_content
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            raise


class MongoDBHandler:
    """Handles interactions with MongoDB."""

    @staticmethod
    def get_all_categories():
        from Utils import MongoDBClient
        mongo_client = MongoDBClient()
        try:
            categories = mongo_client.get_all_categories()
            logger.info("Successfully fetched all categories from MongoDB.")
            return categories
        except Exception as e:
            logger.error(f"Error fetching categories from MongoDB: {e}")
            raise


class DataFrameUtils:
    """Contains utility functions for DataFrame operations."""
    @staticmethod
    def print_dataframe(df: pd.DataFrame, num: int = 10, head: bool=True):
        """Print the DataFrame using tabulate."""
        try:
            if head:
                print(tabulate(df.head(num), df.columns, tablefmt="pretty"))
            else:
                print(tabulate(df.tail(num), df.columns, tablefmt="pretty"))
        except Exception as e:
            logger.error(f"Error printing DataFrame: {e}")
            raise

    @staticmethod
    def save_dataframe(df: pd.DataFrame, topic: str, path: str = os.getenv('DATAFRAME_SAVE_PATH')):
        """Save the DataFrame to a CSV file."""
        try:
            now = datetime.datetime.now()
            filename = f"{path}{topic}-{now.year}-{now.month}-{now.day}.csv"
            df.head(1).to_csv(filename, index=False)
            logger.info(f"Dataframe saved to {filename}")
            return filename
        except Exception as e:
            logger.error(f"Error saving DataFrame: {e}")
            raise

    @staticmethod
    def combine_dataframes(df1: pd.DataFrame, df2: pd.DataFrame, column: str) -> pd.DataFrame:
        """Combine two DataFrames based on a common column."""
        try:
            combined_df = pd.merge(df1, df2, on=column)
            logger.info("DataFrames combined successfully.")
            return combined_df
        except Exception as e:
            logger.error(f"Error combining DataFrames: {e}")
            raise

    @staticmethod
    def combine_dataframes_sum_frequencies(dataframes: List[pd.DataFrame], key_columns: List[str]) -> pd.DataFrame:
        """
        Combine multiple DataFrames by summing the 'frequency' column for matching keys.

        Args:
            dataframes (list of pd.DataFrame): List of DataFrames to combine.
            key_columns (list of str): Columns to use for merging DataFrames.

        Returns:
            pd.DataFrame: A combined DataFrame with summed 'frequency' values and specified key columns.
        """
        if not dataframes:
            raise ValueError("The list of DataFrames is empty.")
        combined_df = dataframes[0].copy()

        for df in dataframes[1:]:
            combined_df = pd.merge(combined_df, df, on=key_columns, how='outer', suffixes=('_left', '_right'))

            combined_df['frequency'] = combined_df[['frequency_left', 'frequency_right']].sum(axis=1, skipna=True)
            combined_df.drop(columns=['frequency_left', 'frequency_right'], inplace=True)
            combined_df = combined_df[key_columns + ['frequency']]
        combined_df.reset_index(drop=True, inplace=True)

        return combined_df[key_columns + ['frequency']]


    @staticmethod
    def filter_dataframe(df: pd.DataFrame, filters: dict, filter_column_name: str) -> pd.DataFrame:
        """Filter a DataFrame using the provided filters dictionary and return two DataFrames:
            one with the filtered data and another with the excluded data.

            Returns:
                tuple:
                    pd.DataFrame: The DataFrame with rows that do not match the filters.
                    pd.DataFrame: The DataFrame with rows that match the filters
        """
        try:
            # Log the initial state of the DataFrame and filters
            logger.debug(f"Initial DataFrame shape: {df.shape}")
            logger.debug(f"Filter column: {filter_column_name}, Filters: {filters.keys()}")

            # Combine all filter values into a single set
            allowed_values = set()
            for filter_data in filters.values():
                allowed_values.update(filter_data['hanzi'])

            # Ensure the filter column exists
            if filter_column_name not in df.columns:
                raise KeyError(f"Column '{filter_column_name}' not found in DataFrame.")

            # Filter the DataFrame
            filtered_df = df[df[filter_column_name].isin(allowed_values)]
            excluded_df = df[~df[filter_column_name].isin(allowed_values)]

            # Log the resulting shapes
            logger.info(f"DataFrame filtered successfully. Filtered shape: {filtered_df.shape}, Excluded shape: {excluded_df.shape}")
            return excluded_df, filtered_df
        except Exception as e:
            logger.error(f"Error filtering DataFrame: {e}")
            raise


class HSKDataFetcher:
    """Handles fetching and storing HSK-related files."""

    _filters = None
    @classmethod
    def fetch_hsk_files(cls) -> dict:
        """Fetch HSK and other vocabulary files."""
        if cls._filters is None:
            logger.info("Fetching HSK files from URLs.")
            columns = ['hanzi', 'tradicional', 'pinyin1', 'pinyin2', 'space', 'mean']

            # Load HSK data files from URLs into a dictionary
            cls._filters = {
                'hsk1': pd.read_csv('https://raw.githubusercontent.com/aurcode/chinese-words/main/Chinese__HSK-1.txt', sep='\t', names=columns),
                'hsk2': pd.read_csv('https://raw.githubusercontent.com/aurcode/chinese-words/main/Chinese__HSK-2.txt', sep='\t', names=columns),
                'hsk3': pd.read_csv('https://raw.githubusercontent.com/aurcode/chinese-words/main/Chinese__HSK-3.txt', sep='\t', names=columns),
                'df_ting': pd.read_csv('https://raw.githubusercontent.com/aurcode/chinese-words/main/hsk-5-vocabulary.csv', sep=';'),
                'df_hsk5': pd.read_csv('https://raw.githubusercontent.com/aurcode/chinese-words/main/%E5%90%AC%E5%8A%9B-hsk5-vocabulary', sep=';')
            }
            logger.info("HSK files fetched successfully.")
        return cls._filters


class DataUtils:
    """Central utility class for handling data operations."""

    @classmethod
    def read_files_to_uploaded(cls, file_paths: list) -> dict:
        """Read the provided file paths and return a dictionary of file content."""
        uploaded_files = {}
        try:
            for file_path in file_paths:
                file_name = os.path.basename(file_path)
                file_content = FileHandler.read_file(file_path)
                uploaded_files[file_name] = file_content
            logger.info(f"Read {len(uploaded_files)} files successfully.")
            return uploaded_files
        except Exception as e:
            logger.error(f"Error reading files: {e}")
            raise

    @classmethod
    def get_all_categories(cls):
        """Fetch all categories from MongoDB."""
        return MongoDBHandler.get_all_categories()

    @classmethod
    def print_dataframe(cls, df: pd.DataFrame, num: int = 10, head: bool = True):
        """Print the DataFrame using tabulate."""
        DataFrameUtils.print_dataframe(df, num, head)

    @classmethod
    def save_df(cls, df: pd.DataFrame, topic: str, path: str = os.getenv('DATAFRAME_SAVE_PATH')):
        """Save the DataFrame to a CSV file."""
        return DataFrameUtils.save_dataframe(df, topic, path)

    @classmethod
    def combine_dataframes(cls, df1: pd.DataFrame, df2: pd.DataFrame, column: str):
        """Combine two DataFrames on the specified column."""
        return DataFrameUtils.combine_dataframes(df1, df2, column)

    @classmethod
    def combine_dataframes_sum_frequencies(cls, dataframes: List[pd.DataFrame], key_columns: List[str]) -> pd.DataFrame:
        """Combine Two DataFrames on the specified column and sum the frequencies"""
        return DataFrameUtils.combine_dataframes_sum_frequencies(dataframes, key_columns)

    @classmethod
    def filter_dataframe(cls, df: pd.DataFrame, filters: dict, filter_column_name: str):
        """Filter the DataFrame with given filters."""
        return DataFrameUtils.filter_dataframe(df, filters, filter_column_name)

    @classmethod
    def fetch_hsk_files(cls):
        """Fetch HSK files from URLs."""
        return HSKDataFetcher.fetch_hsk_files()

    @classmethod
    def read_csv(cls, file_path: str) -> pd.DataFrame:
        return pd.read_csv(file_path, sep=',')