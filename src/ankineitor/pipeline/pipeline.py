from .transformations import Transformation
from .db_client import SQLAlchemyClient

from typing import List, Optional, Callable, Dict, Any
from loguru import logger
from tqdm import tqdm
import pandas as pd
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import LLMTransformation to check its type
try:
    from .llm_transformation import LLMTransformation
    from .llm_audio_transformation import LLMAudioTransformation
    from .llm_image_prompt_transformation import LLMImagePromptTransformation
    from .llm_image_transformation import LLMImageTransformation
except ImportError:
    # Handle case where llm_transformation might not exist
    LLMTransformation = None
    LLMAudioTransformation = None
    LLMImagePromptTransformation = None
    LLMImageTransformation = None


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

        llm_transform_types = tuple(
            cls
            for cls in (
                LLMTransformation,
                LLMAudioTransformation,
                LLMImagePromptTransformation,
                LLMImageTransformation,
            )
            if cls is not None
        )
        if llm_transform_types:
            for t in transformations:
                if isinstance(t, llm_transform_types):
                    self.llm_transformations.append(t)
                else:
                    self.main_transformations.append(t)
        else:
            logger.warning("LLM transformation classes not found, adding all to main.")
            self.main_transformations = transformations

        # Columns for the *main* pipeline cache
        self.columns = [t.column_name for t in self.main_transformations]
        
        # Log transformation details for debugging
        main_names = [type(t).__name__ for t in self.main_transformations]
        llm_names = [type(t).__name__ for t in self.llm_transformations]
        
        logger.info(
            f"Pipeline initialized for table '{table_name}'. "
            f"Main transforms ({len(self.main_transformations)}): {main_names}, "
            f"LLM transforms ({len(self.llm_transformations)}): {llm_names}"
        )

    def transform_data(self, words: List[str], dev_mode: bool = False) -> pd.DataFrame:
        """
        Transforms a list of Chinese words using the configured pipeline.
        """
        return self.transform_data_with_progress(words=words, dev_mode=dev_mode)

    def transform_data_with_progress(
        self,
        words: List[str],
        dev_mode: bool = False,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> pd.DataFrame:
        """
        Transforms a list of words and optionally emits progress events.
        """
        def emit(event: str, **payload: Any) -> None:
            if progress_callback is None:
                return
            try:
                progress_callback({"event": event, **payload})
            except Exception as exc:
                logger.debug(f"Progress callback failed for event '{event}': {exc}")

        pipeline_started_at = time.perf_counter()
        logger.info(f"Starting pipeline for {len(words)} words...")
        emit("pipeline_start", total_words=len(words))
        if dev_mode:
            words = words[:20]
            logger.warning(f"DEV MODE enabled. Processing only {len(words)} words.")
            emit("dev_mode_applied", total_words=len(words))

        def apply_llm_transform(transform: Transformation, input_df: pd.DataFrame):
            before_cols = list(input_df.columns)
            started_at = time.perf_counter()
            output_df = transform.apply(input_df)
            duration_seconds = time.perf_counter() - started_at
            if output_df is None:
                output_df = input_df
            after_cols = list(output_df.columns)
            new_columns = [col for col in after_cols if col not in before_cols]
            return output_df, new_columns, duration_seconds

        def merge_llm_output(base_df: pd.DataFrame, transform_df: pd.DataFrame) -> pd.DataFrame:
            if self.key_field not in transform_df.columns:
                logger.warning(
                    f"Skipping merge for LLM transform output without '{self.key_field}' column."
                )
                return base_df

            merge_columns = [col for col in transform_df.columns if col != self.key_field]
            if not merge_columns:
                return base_df

            overlap = [col for col in merge_columns if col in base_df.columns]
            if overlap:
                base_df = base_df.drop(columns=overlap)

            merge_frame = transform_df[[self.key_field] + merge_columns].drop_duplicates(
                subset=[self.key_field]
            )
            return pd.merge(base_df, merge_frame, on=self.key_field, how="left")

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
        emit(
            "cache_checked",
            cached_words=len(df_cached),
            new_words=len(new_words),
            total_unique_words=len(unique_words),
        )

        # 4. Process only new words through the *main* pipeline
        if len(new_words) > 0:
            df_new = pd.DataFrame({self.key_field: new_words})

            # Run each main transformation
            for transform in self.main_transformations:
                transform_name = type(transform).__name__
                emit(
                    "transform_start",
                    stage="main",
                    transform_name=transform_name,
                    input_rows=len(df_new),
                )
                transform_started_at = time.perf_counter()
                df_new = transform.apply(df_new)
                duration_seconds = time.perf_counter() - transform_started_at
                emit(
                    "transform_complete",
                    stage="main",
                    transform_name=transform_name,
                    duration_seconds=duration_seconds,
                    output_columns=list(df_new.columns),
                    output_rows=len(df_new),
                )

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
            logger.info(
                f"LLM transformations to run: {[type(t).__name__ for t in self.llm_transformations]}"
            )
            emit(
                "llm_stage_start",
                total_words=len(df_processed),
                transforms=[type(t).__name__ for t in self.llm_transformations],
            )
            independent_llm_transforms: List[Transformation] = []
            dependent_llm_transforms: List[Transformation] = []
            for llm_transform in self.llm_transformations:
                if (
                    LLMImageTransformation is not None
                    and isinstance(llm_transform, LLMImageTransformation)
                    and not getattr(llm_transform, "requires_master_prompt", False)
                ):
                    independent_llm_transforms.append(llm_transform)
                else:
                    dependent_llm_transforms.append(llm_transform)

            image_parallel_capable = any(
                int(getattr(transform, "max_workers", 1) or 1) > 1
                for transform in independent_llm_transforms
            )
            run_parallel_image = (
                len(independent_llm_transforms) > 0
                and len(dependent_llm_transforms) > 0
                and image_parallel_capable
            )

            if run_parallel_image:
                logger.info(
                    f"Starting {len(independent_llm_transforms)} image transform(s) in parallel "
                    "with other LLM transforms."
                )
                image_input_df = df_processed.copy()
                future_to_transform = {}
                with ThreadPoolExecutor(
                    max_workers=max(1, len(independent_llm_transforms))
                ) as executor:
                    for independent_transform in independent_llm_transforms:
                        transform_name = type(independent_transform).__name__
                        emit(
                            "transform_start",
                            stage="llm",
                            transform_name=transform_name,
                            input_rows=len(image_input_df),
                        )
                        future = executor.submit(
                            apply_llm_transform, independent_transform, image_input_df.copy()
                        )
                        future_to_transform[future] = independent_transform

                    for llm_transform in dependent_llm_transforms:
                        transform_name = type(llm_transform).__name__
                        logger.info(f"Running {transform_name}...")
                        emit(
                            "transform_start",
                            stage="llm",
                            transform_name=transform_name,
                            input_rows=len(df_processed),
                        )
                        df_processed, new_columns, duration_seconds = apply_llm_transform(
                            llm_transform, df_processed
                        )
                        logger.info(f"{transform_name} complete. New columns: {new_columns}")
                        emit(
                            "transform_complete",
                            stage="llm",
                            transform_name=transform_name,
                            duration_seconds=duration_seconds,
                            new_columns=new_columns,
                            output_rows=len(df_processed),
                        )

                    for future in as_completed(future_to_transform):
                        llm_transform = future_to_transform[future]
                        transform_name = type(llm_transform).__name__
                        try:
                            transform_df, new_columns, duration_seconds = future.result()
                            logger.info(
                                f"{transform_name} complete (parallel). New columns: {new_columns}"
                            )
                            df_processed = merge_llm_output(df_processed, transform_df)
                            emit(
                                "transform_complete",
                                stage="llm",
                                transform_name=transform_name,
                                duration_seconds=duration_seconds,
                                new_columns=new_columns,
                                output_rows=len(df_processed),
                            )
                        except Exception as exc:
                            logger.error(f"{transform_name} failed in parallel: {exc}")
                            emit(
                                "transform_complete",
                                stage="llm",
                                transform_name=transform_name,
                                duration_seconds=0.0,
                                new_columns=[],
                                output_rows=len(df_processed),
                                error=str(exc),
                            )
            else:
                for llm_transform in self.llm_transformations:
                    transform_name = type(llm_transform).__name__
                    logger.info(f"Running {transform_name}...")
                    emit(
                        "transform_start",
                        stage="llm",
                        transform_name=transform_name,
                        input_rows=len(df_processed),
                    )
                    df_processed, new_columns, duration_seconds = apply_llm_transform(
                        llm_transform, df_processed
                    )
                    logger.info(f"{transform_name} complete. New columns: {new_columns}")
                    emit(
                        "transform_complete",
                        stage="llm",
                        transform_name=transform_name,
                        duration_seconds=duration_seconds,
                        new_columns=new_columns,
                        output_rows=len(df_processed),
                    )
            logger.info("LLM transformations complete.")
            emit("llm_stage_complete")

        # 8. Merge with original list to preserve order and duplicates

        # Get all columns from the final processed DataFrame
        final_columns = list(df_processed.columns)

        df_final = pd.merge(
            df_original, df_processed[final_columns], on=self.key_field, how="left"
        )

        # Clean up duplicates that merge might create
        df_final = df_final.drop_duplicates(subset=[self.key_field])

        logger.info(f"Pipeline complete. Returning {len(df_final)} records.")
        emit(
            "pipeline_complete",
            total_duration_seconds=time.perf_counter() - pipeline_started_at,
            output_rows=len(df_final),
            output_columns=list(df_final.columns),
        )
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
