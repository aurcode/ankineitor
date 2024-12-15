import os
import datetime
import pandas as pd
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
    def filter_dataframe(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
        """Filter a DataFrame using the provided filters dictionary."""
        try:
            for filter_name, filter_data in filters.items():
                df = df[df[filter_name].isin(filter_data)]
            logger.info("DataFrame filtered successfully.")
            return df
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
    def filter_dataframe(cls, df: pd.DataFrame, filters: dict):
        """Filter the DataFrame with given filters."""
        return DataFrameUtils.filter_dataframe(df, filters)

    @classmethod
    def fetch_hsk_files(cls):
        """Fetch HSK files from URLs."""
        return HSKDataFetcher.fetch_hsk_files()