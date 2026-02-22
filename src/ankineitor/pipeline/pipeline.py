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

    @staticmethod
    def _emit_progress_event(
        progress_callback: Optional[Callable[[Dict[str, Any]], None]],
        event: str,
        **payload: Any,
    ) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback({"event": event, **payload})
        except Exception as exc:
            logger.debug(f"Progress callback failed for event '{event}': {exc}")

    def _load_cached_records(self, unique_words: List[str]) -> pd.DataFrame:
        logger.debug(f"Checking cache for {len(unique_words)} unique words...")
        cached_records = self.db_client.find_many_by_field(
            keys=unique_words,
            table_name=self.table_name,
            field_name=self.key_field,
        )
        return pd.DataFrame(cached_records)

    def _identify_new_words(
        self,
        *,
        unique_words: List[str],
        df_cached: pd.DataFrame,
    ) -> List[str]:
        if df_cached.empty:
            return list(unique_words)

        processed_words = set(df_cached[self.key_field])
        return [word for word in unique_words if word not in processed_words]

    def _identify_backfill_words(
        self,
        *,
        df_cached: pd.DataFrame,
        new_words: List[str],
    ) -> List[Any]:
        backfill_words: List[Any] = []
        if df_cached.empty or not self.main_transformations:
            return backfill_words

        cached_candidates = df_cached[
            ~df_cached[self.key_field].isin(new_words)
        ].copy()
        if cached_candidates.empty:
            return backfill_words

        missing_any = pd.Series(False, index=cached_candidates.index)
        required_columns = [transform.column_name for transform in self.main_transformations]
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
        return backfill_words

    def _build_main_seed_frame(
        self,
        *,
        words_needing_main: List[str],
        backfill_words: List[Any],
        df_cached: pd.DataFrame,
    ) -> pd.DataFrame:
        df_new = pd.DataFrame({self.key_field: words_needing_main})
        if not backfill_words:
            return df_new

        cached_backfill = df_cached[df_cached[self.key_field].isin(backfill_words)].copy()
        if cached_backfill.empty:
            return df_new

        # Seed with cached rows so existing non-missing fields can be preserved.
        df_new = pd.concat([cached_backfill, df_new], ignore_index=True)
        return df_new.drop_duplicates(subset=[self.key_field], keep="first")

    def _run_main_transformations(
        self,
        *,
        df_new: pd.DataFrame,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]],
    ) -> pd.DataFrame:
        for transform in self.main_transformations:
            transform_name = type(transform).__name__
            self._emit_progress_event(
                progress_callback,
                "transform_start",
                stage="main",
                transform_name=transform_name,
                input_rows=len(df_new),
            )
            transform_started_at = time.perf_counter()
            df_new = transform.apply(df_new)
            duration_seconds = time.perf_counter() - transform_started_at
            self._emit_progress_event(
                progress_callback,
                "transform_complete",
                stage="main",
                transform_name=transform_name,
                duration_seconds=duration_seconds,
                output_columns=list(df_new.columns),
                output_rows=len(df_new),
            )
        return df_new

    def _preserve_existing_main_outputs(
        self,
        *,
        df_new: pd.DataFrame,
        df_cached: pd.DataFrame,
        backfill_words: List[Any],
    ) -> pd.DataFrame:
        if not backfill_words or df_cached.empty or not self.columns:
            return df_new

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
        return df_new.reset_index()

    def _persist_new_records(self, *, df_new: pd.DataFrame, new_words: List[str]) -> None:
        if not new_words:
            return

        df_new_only = df_new[df_new[self.key_field].isin(new_words)].copy()
        if df_new_only.empty:
            return

        logger.debug(f"Saving {len(df_new_only)} new records to database...")
        self.db_client.insert_many_records(
            records=df_new_only.to_dict("records"),
            table_name=self.table_name,
        )

    def _persist_backfill_records(
        self,
        *,
        df_new: pd.DataFrame,
        backfill_words: List[Any],
    ) -> None:
        if not backfill_words or not self.columns:
            return

        df_backfill = df_new[df_new[self.key_field].isin(backfill_words)].copy()
        backfill_records = df_backfill.to_dict("records")
        if not backfill_records:
            return

        if hasattr(self.db_client, "insert_many_records_missing_fields"):
            self.db_client.insert_many_records_missing_fields(
                records=backfill_records,
                columns=self.columns,
                table_name=self.table_name,
                field_name=self.key_field,
            )
            return

        for record in backfill_records:
            self.db_client.insert_record(
                record=record,
                columns=self.columns,
                table_name=self.table_name,
                field_name=self.key_field,
            )

    def _combine_cached_and_new_results(
        self,
        *,
        df_cached: pd.DataFrame,
        df_new: pd.DataFrame,
        words_needing_main: List[str],
    ) -> pd.DataFrame:
        if df_cached.empty:
            return df_new

        refreshed_words = set(words_needing_main)
        df_remaining_cached = df_cached[
            ~df_cached[self.key_field].isin(refreshed_words)
        ]
        return pd.concat([df_remaining_cached, df_new], ignore_index=True)

    def _run_main_stage(
        self,
        *,
        df_cached: pd.DataFrame,
        new_words: List[str],
        backfill_words: List[Any],
        progress_callback: Optional[Callable[[Dict[str, Any]], None]],
    ) -> pd.DataFrame:
        words_needing_main = list(new_words) + [
            word for word in backfill_words if word not in new_words
        ]
        if not words_needing_main:
            return df_cached

        df_new = self._build_main_seed_frame(
            words_needing_main=words_needing_main,
            backfill_words=backfill_words,
            df_cached=df_cached,
        )
        df_new = self._run_main_transformations(
            df_new=df_new,
            progress_callback=progress_callback,
        )
        df_new = self._preserve_existing_main_outputs(
            df_new=df_new,
            df_cached=df_cached,
            backfill_words=backfill_words,
        )
        self._persist_new_records(df_new=df_new, new_words=new_words)
        self._persist_backfill_records(df_new=df_new, backfill_words=backfill_words)
        return self._combine_cached_and_new_results(
            df_cached=df_cached,
            df_new=df_new,
            words_needing_main=words_needing_main,
        )

    @staticmethod
    def _apply_llm_transform(
        transform: Transformation,
        input_df: pd.DataFrame,
    ) -> tuple[pd.DataFrame, List[str], float]:
        before_cols = list(input_df.columns)
        started_at = time.perf_counter()
        output_df = transform.apply(input_df)
        duration_seconds = time.perf_counter() - started_at
        if output_df is None:
            output_df = input_df
        after_cols = list(output_df.columns)
        new_columns = [col for col in after_cols if col not in before_cols]
        return output_df, new_columns, duration_seconds

    def _merge_llm_output(self, base_df: pd.DataFrame, transform_df: pd.DataFrame) -> pd.DataFrame:
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

    def _run_llm_stage_sequential(
        self,
        *,
        df_processed: pd.DataFrame,
        llm_transforms: List[Transformation],
        progress_callback: Optional[Callable[[Dict[str, Any]], None]],
    ) -> pd.DataFrame:
        for llm_transform in llm_transforms:
            transform_name = type(llm_transform).__name__
            logger.info(f"Running {transform_name}...")
            self._emit_progress_event(
                progress_callback,
                "transform_start",
                stage="llm",
                transform_name=transform_name,
                input_rows=len(df_processed),
            )
            df_processed, new_columns, duration_seconds = self._apply_llm_transform(
                llm_transform,
                df_processed,
            )
            logger.info(f"{transform_name} complete. New columns: {new_columns}")
            self._emit_progress_event(
                progress_callback,
                "transform_complete",
                stage="llm",
                transform_name=transform_name,
                duration_seconds=duration_seconds,
                new_columns=new_columns,
                output_rows=len(df_processed),
            )
        return df_processed

    def _run_llm_stage_with_parallel_independent(
        self,
        *,
        df_processed: pd.DataFrame,
        independent_llm_transforms: List[Transformation],
        dependent_llm_transforms: List[Transformation],
        progress_callback: Optional[Callable[[Dict[str, Any]], None]],
    ) -> pd.DataFrame:
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
                self._emit_progress_event(
                    progress_callback,
                    "transform_start",
                    stage="llm",
                    transform_name=transform_name,
                    input_rows=len(image_input_df),
                )
                future = executor.submit(
                    self._apply_llm_transform,
                    independent_transform,
                    image_input_df.copy(),
                )
                future_to_transform[future] = independent_transform

            df_processed = self._run_llm_stage_sequential(
                df_processed=df_processed,
                llm_transforms=dependent_llm_transforms,
                progress_callback=progress_callback,
            )

            for future in as_completed(future_to_transform):
                llm_transform = future_to_transform[future]
                transform_name = type(llm_transform).__name__
                try:
                    transform_df, new_columns, duration_seconds = future.result()
                    logger.info(
                        f"{transform_name} complete (parallel). New columns: {new_columns}"
                    )
                    df_processed = self._merge_llm_output(df_processed, transform_df)
                    self._emit_progress_event(
                        progress_callback,
                        "transform_complete",
                        stage="llm",
                        transform_name=transform_name,
                        duration_seconds=duration_seconds,
                        new_columns=new_columns,
                        output_rows=len(df_processed),
                    )
                except Exception as exc:
                    logger.error(f"{transform_name} failed in parallel: {exc}")
                    self._emit_progress_event(
                        progress_callback,
                        "transform_complete",
                        stage="llm",
                        transform_name=transform_name,
                        duration_seconds=0.0,
                        new_columns=[],
                        output_rows=len(df_processed),
                        error=str(exc),
                    )
        return df_processed

    def _partition_llm_transforms(
        self,
    ) -> tuple[List[Transformation], List[Transformation]]:
        independent_llm_transforms: List[Transformation] = []
        dependent_llm_transforms: List[Transformation] = []
        for llm_transform in self.llm_transformations:
            if self._is_parallel_independent_llm_transform(llm_transform):
                independent_llm_transforms.append(llm_transform)
            else:
                dependent_llm_transforms.append(llm_transform)
        return independent_llm_transforms, dependent_llm_transforms

    @staticmethod
    def _should_run_parallel_image(
        independent_llm_transforms: List[Transformation],
        dependent_llm_transforms: List[Transformation],
    ) -> bool:
        image_parallel_capable = any(
            int(getattr(transform, "max_workers", 1) or 1) > 1
            for transform in independent_llm_transforms
        )
        return (
            len(independent_llm_transforms) > 0
            and len(dependent_llm_transforms) > 0
            and image_parallel_capable
        )

    def _run_llm_stage(
        self,
        *,
        df_processed: pd.DataFrame,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]],
    ) -> pd.DataFrame:
        if not self.llm_transformations:
            return df_processed

        logger.info(f"Running LLM transformations on {len(df_processed)} total words...")
        logger.info(
            f"LLM transformations to run: {[type(t).__name__ for t in self.llm_transformations]}"
        )
        self._emit_progress_event(
            progress_callback,
            "llm_stage_start",
            total_words=len(df_processed),
            transforms=[type(t).__name__ for t in self.llm_transformations],
        )

        independent_llm_transforms, dependent_llm_transforms = self._partition_llm_transforms()
        if self._should_run_parallel_image(
            independent_llm_transforms,
            dependent_llm_transforms,
        ):
            df_processed = self._run_llm_stage_with_parallel_independent(
                df_processed=df_processed,
                independent_llm_transforms=independent_llm_transforms,
                dependent_llm_transforms=dependent_llm_transforms,
                progress_callback=progress_callback,
            )
        else:
            df_processed = self._run_llm_stage_sequential(
                df_processed=df_processed,
                llm_transforms=self.llm_transformations,
                progress_callback=progress_callback,
            )

        logger.info("LLM transformations complete.")
        self._emit_progress_event(progress_callback, "llm_stage_complete")
        return df_processed

    def _merge_with_original_input(
        self,
        *,
        df_original: pd.DataFrame,
        df_processed: pd.DataFrame,
    ) -> pd.DataFrame:
        if self.key_field in df_processed.columns:
            df_processed = df_processed.drop_duplicates(subset=[self.key_field])
        else:
            df_processed = pd.DataFrame(columns=[self.key_field])

        final_columns = list(df_processed.columns)
        if self.key_field not in final_columns:
            final_columns = [self.key_field] + final_columns

        return pd.merge(
            df_original,
            df_processed[final_columns],
            on=self.key_field,
            how="left",
        )

    def transform_data_with_progress(
        self,
        words: List[str],
        dev_mode: bool = False,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> pd.DataFrame:
        """
        Transforms a list of words and optionally emits progress events.
        """
        pipeline_started_at = time.perf_counter()
        logger.info(f"Starting pipeline for {len(words)} words...")
        self._emit_progress_event(
            progress_callback,
            "pipeline_start",
            total_words=len(words),
        )
        if dev_mode:
            words = words[:20]
            logger.warning(f"DEV MODE enabled. Processing only {len(words)} words.")
            self._emit_progress_event(
                progress_callback,
                "dev_mode_applied",
                total_words=len(words),
            )

        # 1. Create initial DataFrame with unique words
        df_original = pd.DataFrame({self.key_field: words})
        unique_words = list(df_original[self.key_field].unique())

        # 2. Check cache (DB) in bulk for *main* transforms
        df_cached = self._load_cached_records(unique_words)

        # 3. Identify new words to process for *main* transforms
        new_words = self._identify_new_words(
            unique_words=unique_words,
            df_cached=df_cached,
        )

        # 3b. Identify cached words that still need selected main outputs.
        backfill_words = self._identify_backfill_words(
            df_cached=df_cached,
            new_words=new_words,
        )

        logger.info(
            "Found {cached} cached words. Processing {new_count} new words and "
            "{backfill_count} cached words missing selected main outputs."
            .format(
                cached=len(df_cached),
                new_count=len(new_words),
                backfill_count=len(backfill_words),
            )
        )
        self._emit_progress_event(
            progress_callback,
            "cache_checked",
            cached_words=len(df_cached),
            new_words=len(new_words),
            backfill_words=len(backfill_words),
            total_unique_words=len(unique_words),
        )

        # 4. Process new words and cached words that need backfilling through main pipeline
        df_processed = self._run_main_stage(
            df_cached=df_cached,
            new_words=new_words,
            backfill_words=backfill_words,
            progress_callback=progress_callback,
        )

        # 7. (NEW STEP) Run LLM transformations on the *entire* processed set
        # This leverages the LLM's own internal caching.
        df_processed = self._run_llm_stage(
            df_processed=df_processed,
            progress_callback=progress_callback,
        )

        # 8. Merge with original list to preserve input order and duplicates.
        df_final = self._merge_with_original_input(
            df_original=df_original,
            df_processed=df_processed,
        )

        logger.info(f"Pipeline complete. Returning {len(df_final)} records.")
        self._emit_progress_event(
            progress_callback,
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
