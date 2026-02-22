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
        for transform in transformations:
            stage = self._resolve_transform_stage(
                transform=transform,
                llm_transform_types=llm_transform_types,
            )
            if stage == "llm":
                self.llm_transformations.append(transform)
            else:
                self.main_transformations.append(transform)

        if not llm_transform_types and self.llm_transformations:
            logger.warning(
                "LLM stage classification is using metadata only; legacy LLM classes were not imported."
            )

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

    @staticmethod
    def _resolve_transform_stage(
        transform: Transformation,
        llm_transform_types: tuple[type, ...],
    ) -> str:
        configured_stage = (
            str(getattr(transform, "pipeline_stage", "") or "").strip().lower()
        )
        if configured_stage == "llm":
            return configured_stage
        if llm_transform_types and isinstance(transform, llm_transform_types):
            return "llm"
        if configured_stage == "main":
            return configured_stage
        return "main"

    @staticmethod
    def _required_input_columns(transform: Transformation) -> tuple[str, ...]:
        required_columns = getattr(transform, "required_input_columns", ())
        if not isinstance(required_columns, (list, tuple, set)):
            return ()
        return tuple(str(col).strip() for col in required_columns if str(col).strip())

    @staticmethod
    def _is_parallel_independent_llm_transform(transform: Transformation) -> bool:
        if TransformationPipeline._required_input_columns(transform):
            return False

        parallel_mode = str(getattr(transform, "llm_parallel_mode", "") or "").strip().lower()
        if parallel_mode == "parallel_independent":
            return True

        # Backward compatibility for transforms that have not adopted metadata yet.
        if (
            LLMImageTransformation is not None
            and isinstance(transform, LLMImageTransformation)
            and not getattr(transform, "requires_master_prompt", False)
        ):
            return True
        return False

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
        new_words = list(new_words)

        # 3b. Identify cached words that still need selected main outputs.
        backfill_words: List[Any] = []
        if not df_cached.empty and self.main_transformations:
            cached_candidates = df_cached[
                ~df_cached[self.key_field].isin(new_words)
            ].copy()
            if not cached_candidates.empty:
                missing_any = pd.Series(False, index=cached_candidates.index)
                required_columns = [t.column_name for t in self.main_transformations]
                for column in required_columns:
                    if column not in cached_candidates.columns:
                        missing_any = pd.Series(True, index=cached_candidates.index)
                        break

                    column_values = cached_candidates[column]
                    normalized = column_values.where(column_values.notna(), "")
                    column_missing = normalized.astype(str).str.strip().eq("")
                    missing_any = missing_any | column_missing
                    if missing_any.all():
                        break

                backfill_words = cached_candidates.loc[
                    missing_any, self.key_field
                ].tolist()

        logger.info(
            "Found {cached} cached words. Processing {new_count} new words and "
            "{backfill_count} cached words missing selected main outputs."
            .format(
                cached=len(df_cached),
                new_count=len(new_words),
                backfill_count=len(backfill_words),
            )
        )
        emit(
            "cache_checked",
            cached_words=len(df_cached),
            new_words=len(new_words),
            backfill_words=len(backfill_words),
            total_unique_words=len(unique_words),
        )

        # 4. Process new words and cached words that need backfilling through main pipeline
        words_needing_main = list(new_words) + [
            word for word in backfill_words if word not in new_words
        ]
        if len(words_needing_main) > 0:
            df_new = pd.DataFrame({self.key_field: words_needing_main})
            if backfill_words:
                cached_backfill = df_cached[
                    df_cached[self.key_field].isin(backfill_words)
                ].copy()
                if not cached_backfill.empty:
                    # Seed with cached rows so existing non-missing fields can be preserved.
                    df_new = pd.concat([cached_backfill, df_new], ignore_index=True)
                    df_new = df_new.drop_duplicates(
                        subset=[self.key_field], keep="first"
                    )

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

            # Preserve existing non-missing main outputs for cached backfill rows.
            if backfill_words and not df_cached.empty and self.columns:
                cached_backfill = (
                    df_cached[df_cached[self.key_field].isin(backfill_words)]
                    .copy()
                    .set_index(self.key_field)
                )
                df_new = df_new.copy().set_index(self.key_field)
                for column in self.columns:
                    if column not in df_new.columns or column not in cached_backfill.columns:
                        continue
                    previous_values = cached_backfill[column].reindex(df_new.index)
                    normalized_previous = previous_values.where(previous_values.notna(), "")
                    preserve_mask = ~normalized_previous.astype(str).str.strip().eq("")
                    if preserve_mask.any():
                        df_new.loc[preserve_mask, column] = previous_values[preserve_mask]
                df_new = df_new.reset_index()

            # 5. Save truly new records in bulk
            if len(new_words) > 0:
                df_new_only = df_new[df_new[self.key_field].isin(new_words)].copy()
                if not df_new_only.empty:
                    logger.debug(
                        f"Saving {len(df_new_only)} new records to database..."
                    )
                    self.db_client.insert_many_records(
                        records=df_new_only.to_dict("records"), table_name=self.table_name
                    )

            # 5b. Backfill cached records with missing fields.
            if backfill_words and self.columns:
                df_backfill = df_new[df_new[self.key_field].isin(backfill_words)].copy()
                backfill_records = df_backfill.to_dict("records")
                if backfill_records:
                    if hasattr(self.db_client, "insert_many_records_missing_fields"):
                        self.db_client.insert_many_records_missing_fields(
                            records=backfill_records,
                            columns=self.columns,
                            table_name=self.table_name,
                            field_name=self.key_field,
                        )
                    else:
                        for record in backfill_records:
                            self.db_client.insert_record(
                                record=record,
                                columns=self.columns,
                                table_name=self.table_name,
                                field_name=self.key_field,
                            )

            # 6. Combine cached and refreshed/new results
            if df_cached.empty:
                df_processed = df_new
            else:
                refreshed_words = set(words_needing_main)
                df_remaining_cached = df_cached[
                    ~df_cached[self.key_field].isin(refreshed_words)
                ]
                df_processed = pd.concat(
                    [df_remaining_cached, df_new], ignore_index=True
                )
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
                if self._is_parallel_independent_llm_transform(llm_transform):
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

        # 8. Merge with original list to preserve input order and duplicates.
        if self.key_field in df_processed.columns:
            df_processed = df_processed.drop_duplicates(subset=[self.key_field])

        # Get all columns from the final processed DataFrame
        final_columns = list(df_processed.columns)

        df_final = pd.merge(
            df_original, df_processed[final_columns], on=self.key_field, how="left"
        )

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
