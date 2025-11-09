# Assume SQLAlchemyClient is in a file named `db_client.py`
from db_client import SQLAlchemyClient
from typing import List, Optional
from loguru import logger
import pandas as pd
from transformations import Transformation
from tqdm import tqdm


class TransformationPipeline:
    """
    Manages the full ETL pipeline:
    1. Check cache (DB)
    2. Process only new items
    3. Save new items to cache (DB)
    4. Return combined results
    """

    def __init__(
        self,
        db_client: SQLAlchemyClient,
        transformations: List[Transformation],
        table_name: str = "hanzi_processing",
        key_field: str = "word",
    ):
        self.db_client = db_client
        self.transformations = transformations
        self.table_name = table_name
        self.key_field = key_field
        # Get all column names from the transformations
        self.columns = [t.column_name for t in self.transformations]
        logger.info(f"Pipeline initialized for table '{table_name}'.")

    def transform_data(self, words: List[str], dev_mode: bool = False) -> pd.DataFrame:
        """
        Transforms a list of Chinese words using the configured pipeline.
        """
        logger.info(f"Starting pipeline for {len(words)} words...")
        if dev_mode:
            words = words[:20]
            logger.warning(f"DEV MODE enabled. Processing only {len(words)} words.")

        # 1. Create initial DataFrame with unique words
        df_original = pd.DataFrame({self.key_field: words})
        unique_words = df_original[self.key_field].unique()

        # 2. Check cache (DB) in bulk
        logger.debug(f"Checking cache for {len(unique_words)} unique words...")
        cached_records = self.db_client.find_many_by_field(
            keys=unique_words, table_name=self.table_name, field_name=self.key_field
        )
        df_cached = pd.DataFrame(cached_records)

        # 3. Identify new words to process
        if not df_cached.empty:
            processed_words = set(df_cached[self.key_field])
            new_words = [w for w in unique_words if w not in processed_words]
        else:
            new_words = unique_words

        logger.info(
            f"Found {len(df_cached)} cached words. Processing {len(new_words)} new words."
        )

        # 4. Process only new words through the pipeline
        if len(new_words) > 0:
            df_new = pd.DataFrame({self.key_field: new_words})

            # Run each transformation
            for transform in self.transformations:
                df_new = transform.apply(df_new)

            # 5. Save new results to cache (DB) in bulk
            logger.debug(f"Saving {len(df_new)} new records to database...")
            new_records = df_new.to_dict("records")
            self.db_client.insert_many_records(
                records=new_records, table_name=self.table_name
            )

            # 6. Combine cached and new results
            df_processed = pd.concat([df_cached, df_new], ignore_index=True)
        else:
            df_processed = df_cached  # No new words, just use cached data

        # 7. Merge with original list to preserve order and duplicates
        final_columns = [self.key_field] + [
            col for col in self.columns if col in df_processed
        ]
        df_final = pd.merge(
            df_original, df_processed[final_columns], on=self.key_field, how="left"
        )

        # Clean up duplicates that merge might create
        df_final = df_final.drop_duplicates(subset=[self.key_field])

        logger.info(f"Pipeline complete. Returning {len(df_final)} records.")
        return df_final

    def transform_categories(
        self, df: pd.DataFrame, category: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Adds or updates categories for a DataFrame of processed words.
        """
        logger.info("Transforming categories...")
        if "word" not in df.columns:
            logger.error("DataFrame must have a 'word' column for category transform.")
            return df

        # This can be vectorized with .apply()
        def _add_and_get_cats(word: str) -> str:
            if category:
                self.db_client.add_category(
                    key=word,
                    new_category=category,
                    table_name=self.table_name,
                    field_name=self.key_field,
                )
            categories = self.db_client.get_categories_by_word(
                key=word, table_name=self.table_name
            )
            return ", ".join(categories)

        tqdm.pandas(desc="Updating categories")
        df["categories"] = df[self.key_field].progress_apply(_add_and_get_cats)
        return df.reset_index(drop=True)
