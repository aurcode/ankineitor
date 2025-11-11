from .transformations import Transformation
from .db_client import SQLAlchemyClient

from typing import List, Optional
from loguru import logger
from tqdm import tqdm
import pandas as pd

# Import LLMTransformation to check its type
try:
    from .llm_transformation import LLMTransformation
except ImportError:
    # Handle case where llm_transformation might not exist
    LLMTransformation = None


class TransformationPipeline:
    """
    Manages the full ETL pipeline:
    1. Check cache (DB) for main transforms
    2. Process only new items with main transforms
    3. Save new items to cache (DB)
    4. Run "post-processing" transforms (like LLM) on the *entire* dataset
    5. Return combined results
    """

    def __init__(
        self,
        db_client: SQLAlchemyClient,
        transformations: List[Transformation],
        table_name: str = "hanzi_processing",
        key_field: str = "word",
    ):
        self.db_client = db_client
        self.table_name = table_name
        self.key_field = key_field

        # Separate LLM transforms from main transforms
        self.main_transformations: List[Transformation] = []
        self.llm_transformations: List[Transformation] = []

        if LLMTransformation:  # Check if class was imported
            for t in transformations:
                if isinstance(t, LLMTransformation):
                    self.llm_transformations.append(t)
                else:
                    self.main_transformations.append(t)
        else:
            logger.warning("LLMTransformation class not found, adding all to main.")
            self.main_transformations = transformations

        # Columns for the *main* pipeline cache
        self.columns = [t.column_name for t in self.main_transformations]
        logger.info(
            f"Pipeline initialized for table '{table_name}'. "
            f"Main transforms: {len(self.main_transformations)}, "
            f"LLM transforms: {len(self.llm_transformations)}"
        )

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

        # 2. Check cache (DB) in bulk for *main* transforms
        logger.debug(f"Checking cache for {len(unique_words)} unique words...")
        cached_records = self.db_client.find_many_by_field(
            keys=unique_words, table_name=self.table_name, field_name=self.key_field
        )
        df_cached = pd.DataFrame(cached_records)

        # 3. Identify new words to process for *main* transforms
        if not df_cached.empty:
            processed_words = set(df_cached[self.key_field])
            new_words = [w for w in unique_words if w not in processed_words]
        else:
            new_words = unique_words

        logger.info(
            f"Found {len(df_cached)} cached words. Processing {len(new_words)} new words with main transforms."
        )

        # 4. Process only new words through the *main* pipeline
        if len(new_words) > 0:
            df_new = pd.DataFrame({self.key_field: new_words})

            # Run each main transformation
            for transform in self.main_transformations:
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

        # 7. (NEW STEP) Run LLM transformations on the *entire* processed set
        # This leverages the LLM's own internal caching.
        if self.llm_transformations:
            logger.info(
                f"Running LLM transformations on {len(df_processed)} total words..."
            )
            for llm_transform in self.llm_transformations:
                # The llm_transform.apply method will handle its own caching
                # and merge columns back into df_processed
                df_processed = llm_transform.apply(df_processed)
            logger.info("LLM transformations complete.")

        # 8. Merge with original list to preserve order and duplicates

        # Get all columns from the final processed DataFrame
        final_columns = list(df_processed.columns)

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


if __name__ == "__main__":
    import os
    from db_client import SQLAlchemyClient
    from audio_creator import AudioCreator
    from transformations import (
        Transformation,
        PinyinTransformation,
        TranslationTransformation,
        AudioTransformation,
        TimestampTransformation,
    )
    from llm_transformation import LLMTransformation
    from loguru import logger
    from typing import List

    # --- Setup Logging ---
    # Ensure logs directory exists
    os.makedirs("logs", exist_ok=True)
    logger.add("logs/pipeline.log", rotation="10 MB", level="INFO")
    logger.add("logs/pipeline_debug.log", rotation="10 MB", level="DEBUG", enqueue=True)
    logger.info("--- Starting New Pipeline Job ---")

    # 1. Setup Dependencies

    # This client manages the *main pipeline* cache
    # It stores the *final* processed data (pinyin, translation, audio path, etc.)
    pipeline_db_client = SQLAlchemyClient(db_path="ankineitor_pipeline.db")

    # This client *only* manages the cache for *LLM inference*
    # This separation is good: it caches raw API results.
    llm_db_client = SQLAlchemyClient(db_path="ankineitor_llm_cache.db")

    # This handles audio file creation
    audio_creator = AudioCreator(folder_name="./my_audio_files")

    # 2. Define the pipeline transformations
    # We can now add LLMTransformation just like any other
    my_transformations: List[Transformation] = [
        PinyinTransformation(),
        TranslationTransformation(lan_in="zh-CN", lan_out="es"),
        AudioTransformation(audio_creator=audio_creator),
        TimestampTransformation(),
        # Add the refactored LLMTransformation
        # We inject its dedicated database client
        LLMTransformation(db_client=llm_db_client),
    ]

    # 3. Initialize the pipeline
    # We pass the *pipeline's* db client here
    pipeline = TransformationPipeline(
        db_client=pipeline_db_client,
        transformations=my_transformations,
        table_name="hanzi_processing",  # Main table for processed words
    )

    # 4. Define words and run the pipeline
    words_to_process = [
        "你好",  # Hello
        "谢谢",  # Thank you
        "数据",  # Data
        "工程师",  # Engineer
        "你好",  # Duplicate (tests pipeline caching)
        "苹果",  # Apple
        "熊猫",  # Panda (New)
    ]

    try:
        # dev_mode=True processes only the first 20 words
        df_results = pipeline.transform_data(words_to_process, dev_mode=False)

        print("\n--- Final Processed Data ---")
        print(df_results)

        # Save results to CSV
        df_results.to_csv("pipeline_results.csv", index=False)
        logger.info("Pipeline results saved to 'pipeline_results.csv'")

        # 5. (Optional) Add categories to the results
        # This step runs *after* the main pipeline processing
        logger.info("Adding 'HSK1' category to all processed words...")
        df_categorized = pipeline.transform_categories(df_results, category="HSK1")

        print("\n--- Final Categorized Data ---")
        print(df_categorized)
        df_categorized.to_csv("pipeline_results_categorized.csv", index=False)
        logger.info("Categorized results saved to 'pipeline_results_categorized.csv'")

    except Exception as e:
        logger.critical(f"An unhandled error occurred in the pipeline: {e}")

    finally:
        # 6. Close DB connections
        pipeline_db_client.close()
        llm_db_client.close()
        logger.info("Database connections closed. Job complete.")
        print("\nJob complete. Check logs/pipeline.log for details.")
