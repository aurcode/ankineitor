import os
import datetime
import pandas as pd
from typing import List
from dotenv import load_dotenv
from tabulate import tabulate
from loguru import logger
from typing import List, Dict

# Load environment variables
load_dotenv()


class FileHandler:
    """Handles file operations such as reading and loading files."""

    @staticmethod
    def read_file(file_path: str) -> bytes:
        """Read a file and return its content as bytes."""
        try:
            with open(file_path, "rb") as file:
                file_content = file.read()
            logger.info(f"Successfully read file: {file_path}")
            return file_content
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            raise


# NOTE: Removed MongoDBHandler as requested, since you are moving to SQLAlchemy
# class MongoDBHandler: ...


class DataFrameUtils:
    """Contains utility functions for DataFrame operations."""

    @staticmethod
    def print_dataframe(df: pd.DataFrame, num: int = 10, head: bool = True):
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
    def save_dataframe(
        df: pd.DataFrame, topic: str, path: str = os.getenv("DATAFRAME_SAVE_PATH")
    ):
        """Save the DataFrame to a CSV file."""
        try:
            path = (
                "/opt/audio/"
                if os.getenv("DOCKER")
                else os.getenv("AUDIO_PATH") if path else path
            )
            now = datetime.datetime.now()
            filename = f"{path}{topic}-{now.year}-{now.month}-{now.day}.csv"
            df.head(1).to_csv(filename, index=False)
            logger.info(f"Dataframe saved to {filename}")
            return filename
        except Exception as e:
            logger.error(f"Error saving DataFrame: {e}")
            raise

    @staticmethod
    def combine_dataframes(
        df1: pd.DataFrame, df2: pd.DataFrame, column: str
    ) -> pd.DataFrame:
        """Combine two DataFrames based on a common column."""
        try:
            combined_df = pd.merge(df1, df2, on=column)
            logger.info("DataFrames combined successfully.")
            return combined_df
        except Exception as e:
            logger.error(f"Error combining DataFrames: {e}")
            raise

    @staticmethod
    def combine_dataframes_sum_frequencies(
        dataframes: List[pd.DataFrame], key_columns: List[str]
    ) -> pd.DataFrame:
        """
        Combine multiple DataFrames by summing the 'frequency' column for matching keys.
        (This is the logic you provided)
        """
        if not dataframes:
            raise ValueError("The list of DataFrames is empty.")

        # Ensure all DataFrames have the 'frequency' column, fill with 0 if not
        for i, df in enumerate(dataframes):
            if "frequency" not in df.columns:
                logger.warning(
                    f"DataFrame {i} missing 'frequency' column, filling with 0."
                )
                df["frequency"] = 0
            # Ensure frequency is numeric, coerce errors to NaN, then fillna
            df["frequency"] = pd.to_numeric(df["frequency"], errors="coerce").fillna(0)

        combined_df = dataframes[0].copy()

        for df in dataframes[1:]:
            combined_df = pd.merge(
                combined_df,
                df,
                on=key_columns,
                how="outer",
                suffixes=("_left", "_right"),
            )

            # Sum 'frequency_left' and 'frequency_right'
            freq_left = combined_df["frequency_left"].fillna(0)
            freq_right = combined_df["frequency_right"].fillna(0)

            combined_df["frequency"] = freq_left + freq_right

            # Drop the intermediate columns
            drop_cols = [
                col for col in combined_df.columns if col.endswith(("_left", "_right"))
            ]
            combined_df.drop(columns=drop_cols, inplace=True)

            # Re-select only the columns we care about to avoid cruft
            combined_df = combined_df[key_columns + ["frequency"]]

        combined_df.reset_index(drop=True, inplace=True)
        return combined_df[key_columns + ["frequency"]]

    @staticmethod
    def filter_dataframe(
        df: pd.DataFrame, filters: dict, filter_column_name: str
    ) -> pd.DataFrame:
        """
        Filter a DataFrame using a dictionary of filters.

        Returns a tuple of two DataFrames:
        1.  remaining_df: Rows from the original df that were NOT in any filter.
        2.  removed_df: Rows that WERE found in the filters, with an added
            'hsk_level' column indicating which filter they matched.
        """
        try:
            logger.debug(f"Initial DataFrame shape: {df.shape}")
            logger.debug(f"Filter column: {filter_column_name}, Filters applied: {list(filters.keys())}")

            if filter_column_name not in df.columns:
                raise KeyError(f"Column '{filter_column_name}' not found in DataFrame.")

            remaining_df = df.copy()
            removed_chunks = []

            # Iterate through each HSK filter provided
            for level, filter_df in filters.items():
                if "hanzi" not in filter_df.columns:
                    logger.warning(f"Filter '{level}' is missing 'hanzi' column, skipping.")
                    continue

                # Get the set of words for the current HSK level
                hsk_words = set(filter_df["hanzi"])

                # Find which rows in the *currently remaining* df match this HSK level
                is_in_level = remaining_df[filter_column_name].isin(hsk_words)
                
                if is_in_level.any():
                    # Extract the rows to be removed
                    removed_chunk = remaining_df[is_in_level].copy()
                    removed_chunk["hsk_level"] = level.upper()  # Add the new column
                    removed_chunks.append(removed_chunk)

                    # Update remaining_df by keeping only the non-matching rows
                    remaining_df = remaining_df[~is_in_level]

            # Combine all removed chunks into a single DataFrame
            if removed_chunks:
                removed_df = pd.concat(removed_chunks, ignore_index=True)
            else:
                removed_df = pd.DataFrame(columns=list(df.columns) + ["hsk_level"])

            logger.info(
                f"DataFrame filtered. Remaining shape: {remaining_df.shape}, Removed shape: {removed_df.shape}"
            )
            return remaining_df, removed_df

        except Exception as e:
            logger.error(f"Error filtering DataFrame: {e}")
            raise


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

    # NOTE: Removed get_all_categories as it was tied to MongoDB
    # @classmethod
    # def get_all_categories(cls): ...

    @classmethod
    def print_dataframe(cls, df: pd.DataFrame, num: int = 10, head: bool = True):
        """Print the DataFrame using tabulate."""
        DataFrameUtils.print_dataframe(df, num, head)

    @classmethod
    def save_df(
        cls, df: pd.DataFrame, topic: str, path: str = os.getenv("DATAFRAME_SAVE_PATH")
    ):
        """Save the DataFrame to a CSV file."""
        return DataFrameUtils.save_dataframe(df, topic, path)

    @classmethod
    def combine_dataframes(cls, df1: pd.DataFrame, df2: pd.DataFrame, column: str):
        """Combine two DataFrames on the specified column."""
        return DataFrameUtils.combine_dataframes(df1, df2, column)

    @classmethod
    def combine_dataframes_sum_frequencies(
        cls, dataframes: List[pd.DataFrame], key_columns: List[str]
    ) -> pd.DataFrame:
        """Combine Two DataFrames on the specified column and sum the frequencies"""
        return DataFrameUtils.combine_dataframes_sum_frequencies(
            dataframes, key_columns
        )

    @classmethod
    def filter_dataframe(cls, df: pd.DataFrame, filters: dict, filter_column_name: str):
        """Filter the DataFrame with given filters."""
        return DataFrameUtils.filter_dataframe(df, filters, filter_column_name)

    @classmethod
    def read_csv(cls, file_path: str) -> pd.DataFrame:
        return pd.read_csv(file_path, sep=",")
