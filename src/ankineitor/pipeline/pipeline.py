from .transformations import Transformation
from .db_client import SQLAlchemyClient

from typing import List, Optional, Callable, Dict, Any
from loguru import logger
from tqdm import tqdm
import pandas as pd
import time
import re
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, as_completed, wait

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
        self.ordered_transformations: List[Transformation] = list(transformations)

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

    def _progress_word_from_df(self, df: pd.DataFrame) -> str:
        if df.empty or self.key_field not in df.columns:
            return ""
        value = df.iloc[0].get(self.key_field, "")
        try:
            if pd.isna(value):
                return ""
        except Exception:
            pass
        return str(value)

    @staticmethod
    def _progress_words_left(total_rows: int) -> int:
        return max(int(total_rows) - 1, 0)

    @staticmethod
    def _payload_value_present(value: Any) -> bool:
        if value is None:
            return False
        try:
            if pd.isna(value):
                return False
        except Exception:
            pass
        if isinstance(value, str):
            return bool(value.strip())
        return True

    def _cached_rows_by_word(
        self,
        *,
        df_cached: pd.DataFrame,
        unique_words: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        if df_cached.empty or self.key_field not in df_cached.columns:
            return {}

        allowed_words = set(unique_words)
        cached_rows: Dict[str, Dict[str, Any]] = {}
        for row in df_cached.to_dict("records"):
            safe_word = str(row.get(self.key_field, "") or "").strip()
            if not safe_word or safe_word not in allowed_words or safe_word in cached_rows:
                continue
            normalized_row = dict(row)
            normalized_row[self.key_field] = safe_word
            cached_rows[safe_word] = normalized_row
        return cached_rows

    def _is_transform_output_complete_for_word(
        self,
        *,
        transform: Transformation,
        row_payload: Dict[str, Any],
    ) -> bool:
        output_columns = getattr(transform, "output_columns", ())
        if isinstance(output_columns, (list, tuple, set)):
            normalized_output_columns = [
                str(column).strip() for column in output_columns if str(column).strip()
            ]
            if normalized_output_columns:
                return all(
                    self._payload_value_present(row_payload.get(column))
                    for column in normalized_output_columns
                )

        transform_name = type(transform).__name__
        if transform_name == "LLMAudioTransformation":
            sentence_indexes = set()
            sentence_audio_indexes = set()
            sentence_pattern = re.compile(r"^sentence_(\d+)$")
            tts_clean_pattern = re.compile(r"^sentence_(\d+)_tts_clean$")
            sentence_audio_pattern = re.compile(r"^sentence_(\d+)_audio$")
            for column_name, value in row_payload.items():
                if not self._payload_value_present(value):
                    continue
                normalized_column = str(column_name).strip()
                sentence_match = sentence_pattern.match(normalized_column)
                if sentence_match:
                    sentence_indexes.add(int(sentence_match.group(1)))
                    continue
                tts_clean_match = tts_clean_pattern.match(normalized_column)
                if tts_clean_match:
                    sentence_indexes.add(int(tts_clean_match.group(1)))
                    continue
                sentence_audio_match = sentence_audio_pattern.match(normalized_column)
                if sentence_audio_match:
                    sentence_audio_indexes.add(int(sentence_audio_match.group(1)))

            if not sentence_indexes:
                # Parallel mode seeds this check from cached main-table rows that
                # do not include sentence columns yet. Treat sentence audio as
                # complete only if sentence audio outputs already exist.
                return bool(sentence_audio_indexes)

            for sentence_index in sorted(sentence_indexes):
                if not self._payload_value_present(
                    row_payload.get(f"sentence_{sentence_index}_audio")
                ):
                    return False
            return True

        if transform_name == "LLMImagePromptTransformation":
            if self._payload_value_present(row_payload.get("master_image_prompt")):
                return True
            return self._payload_value_present(
                row_payload.get("image_generation_skip_reason")
            )

        if transform_name == "LLMImageTransformation":
            if self._payload_value_present(row_payload.get("picture")):
                return True
            image_render_status = (
                str(row_payload.get("image_render_status", "") or "").strip().lower()
            )
            return image_render_status in {"cached", "generated", "skipped", "success"}

        output_column = str(getattr(transform, "column_name", "") or "").strip()
        if not output_column:
            return False
        return self._payload_value_present(row_payload.get(output_column))

    def _resolve_word_parallel_dependencies(
        self,
        transforms: List[Transformation],
    ) -> Dict[int, set[int]]:
        dependencies: Dict[int, set[int]] = {idx: set() for idx in range(len(transforms))}
        column_producers: Dict[str, List[int]] = {}

        for idx, transform in enumerate(transforms):
            produced_column = str(getattr(transform, "column_name", "") or "").strip()
            if produced_column:
                column_producers.setdefault(produced_column, []).append(idx)

        for idx, transform in enumerate(transforms):
            for required_column in self._required_input_columns(transform):
                for producer_index in column_producers.get(required_column, []):
                    if producer_index != idx:
                        dependencies[idx].add(producer_index)

            if (
                LLMAudioTransformation is not None
                and isinstance(transform, LLMAudioTransformation)
            ):
                for candidate_index, candidate_transform in enumerate(transforms):
                    if candidate_index == idx:
                        continue
                    if LLMTransformation is not None and isinstance(
                        candidate_transform, LLMTransformation
                    ):
                        dependencies[idx].add(candidate_index)
                        break

            if (
                LLMImageTransformation is not None
                and isinstance(transform, LLMImageTransformation)
            ):
                for candidate_index, candidate_transform in enumerate(transforms):
                    if candidate_index == idx:
                        continue
                    if LLMImagePromptTransformation is not None and isinstance(
                        candidate_transform, LLMImagePromptTransformation
                    ):
                        dependencies[idx].add(candidate_index)
                        break

        return dependencies

    def _build_parallel_transform_input(
        self,
        *,
        base_df: pd.DataFrame,
        dependency_indexes: set[int],
        transform_outputs: Dict[int, pd.DataFrame],
    ) -> pd.DataFrame:
        input_df = base_df.copy()
        for dependency_index in sorted(dependency_indexes):
            dependency_df = transform_outputs.get(dependency_index)
            if dependency_df is None:
                continue
            input_df = self._merge_llm_output(input_df, dependency_df)
        return input_df

    def _build_parallel_word_input(
        self,
        *,
        word: str,
        dependency_indexes: set[int],
        transform_word_outputs: Dict[int, Dict[str, Dict[str, Any]]],
    ) -> pd.DataFrame:
        row_payload: Dict[str, Any] = {self.key_field: word}
        for dependency_index in sorted(dependency_indexes):
            dependency_rows = transform_word_outputs.get(dependency_index, {})
            dependency_row = dependency_rows.get(word)
            if not dependency_row:
                continue
            for column_name, value in dependency_row.items():
                if str(column_name) == self.key_field:
                    continue
                row_payload[str(column_name)] = value
        return pd.DataFrame([row_payload])

    def _extract_parallel_word_output(
        self,
        *,
        word: str,
        output_df: Optional[pd.DataFrame],
        fallback_df: pd.DataFrame,
    ) -> Dict[str, Any]:
        source_df = output_df
        if source_df is None or source_df.empty:
            source_df = fallback_df
        if source_df is None or source_df.empty:
            return {self.key_field: word}

        selected_row = None
        if self.key_field in source_df.columns:
            normalized_words = source_df[self.key_field].astype(str)
            matches = source_df[normalized_words == str(word)]
            if not matches.empty:
                selected_row = matches.iloc[0]

        if selected_row is None:
            selected_row = source_df.iloc[0]

        row_payload = {str(column): selected_row.get(column) for column in source_df.columns}
        resolved_word = str(row_payload.get(self.key_field, "") or "").strip()
        row_payload[self.key_field] = resolved_word or str(word)
        return row_payload

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
            current_word = self._progress_word_from_df(df_new)
            words_left = self._progress_words_left(len(df_new))
            self._emit_progress_event(
                progress_callback,
                "transform_start",
                stage="main",
                transform_name=transform_name,
                input_rows=len(df_new),
                current_word=current_word,
                words_left=words_left,
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
                current_word=current_word,
                words_left=0,
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

    def _persist_parallel_main_cache(
        self,
        *,
        df_final: pd.DataFrame,
        new_words: List[str],
        backfill_words: List[str],
    ) -> None:
        if df_final.empty or self.key_field not in df_final.columns or not self.columns:
            return

        cache_columns = [
            self.key_field,
            *[column for column in self.columns if column in df_final.columns],
        ]
        if len(cache_columns) <= 1:
            return

        cache_value_columns = [column for column in cache_columns if column != self.key_field]
        df_cache_payload = (
            df_final[cache_columns]
            .drop_duplicates(subset=[self.key_field])
            .copy()
        )
        if df_cache_payload.empty:
            return

        if new_words:
            df_new_rows = df_cache_payload[
                df_cache_payload[self.key_field].isin(new_words)
            ].copy()
            if not df_new_rows.empty:
                self.db_client.insert_many_records(
                    records=df_new_rows.to_dict("records"),
                    table_name=self.table_name,
                )

        if not backfill_words:
            return

        df_backfill_rows = df_cache_payload[
            df_cache_payload[self.key_field].isin(backfill_words)
        ].copy()
        backfill_records = df_backfill_rows.to_dict("records")
        if not backfill_records:
            return

        if hasattr(self.db_client, "insert_many_records_missing_fields"):
            self.db_client.insert_many_records_missing_fields(
                records=backfill_records,
                columns=cache_value_columns,
                table_name=self.table_name,
                field_name=self.key_field,
            )
            return

        for record in backfill_records:
            self.db_client.insert_record(
                record=record,
                columns=cache_value_columns,
                table_name=self.table_name,
                field_name=self.key_field,
            )

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
            current_word = self._progress_word_from_df(df_processed)
            words_left = self._progress_words_left(len(df_processed))
            self._emit_progress_event(
                progress_callback,
                "transform_start",
                stage="llm",
                transform_name=transform_name,
                input_rows=len(df_processed),
                current_word=current_word,
                words_left=words_left,
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
                current_word=current_word,
                words_left=0,
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
                current_word = self._progress_word_from_df(image_input_df)
                words_left = self._progress_words_left(len(image_input_df))
                self._emit_progress_event(
                    progress_callback,
                    "transform_start",
                    stage="llm",
                    transform_name=transform_name,
                    input_rows=len(image_input_df),
                    current_word=current_word,
                    words_left=words_left,
                )
                future = executor.submit(
                    self._apply_llm_transform,
                    independent_transform,
                    image_input_df.copy(),
                )
                future_to_transform[future] = (independent_transform, current_word)

            df_processed = self._run_llm_stage_sequential(
                df_processed=df_processed,
                llm_transforms=dependent_llm_transforms,
                progress_callback=progress_callback,
            )

            for future in as_completed(future_to_transform):
                llm_transform, current_word = future_to_transform[future]
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
                        current_word=current_word,
                        words_left=0,
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
                        current_word=current_word,
                        words_left=0,
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

    def _transform_data_with_parallel_word_branches(
        self,
        *,
        words: List[str],
        dev_mode: bool = False,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> pd.DataFrame:
        pipeline_started_at = time.perf_counter()
        logger.info(
            f"Starting parallel-word pipeline for {len(words)} words..."
        )
        self._emit_progress_event(
            progress_callback,
            "pipeline_start",
            total_words=len(words),
            execution_mode="parallel_word_branches",
        )
        if dev_mode:
            words = words[:20]
            logger.warning(f"DEV MODE enabled. Processing only {len(words)} words.")
            self._emit_progress_event(
                progress_callback,
                "dev_mode_applied",
                total_words=len(words),
                execution_mode="parallel_word_branches",
            )

        df_original = pd.DataFrame({self.key_field: words})
        unique_words: List[str] = []
        seen_words = set()
        for raw_word in df_original[self.key_field]:
            safe_word = str(raw_word or "").strip()
            if not safe_word or safe_word in seen_words:
                continue
            seen_words.add(safe_word)
            unique_words.append(safe_word)

        if not unique_words:
            self._emit_progress_event(
                progress_callback,
                "pipeline_complete",
                total_duration_seconds=time.perf_counter() - pipeline_started_at,
                output_rows=len(df_original),
                output_columns=list(df_original.columns),
                execution_mode="parallel_word_branches",
            )
            return df_original

        try:
            df_cached = self._load_cached_records(unique_words)
        except Exception as exc:
            logger.warning(f"Cache lookup failed in parallel-word mode: {exc}")
            df_cached = pd.DataFrame({self.key_field: []})

        transforms = list(self.ordered_transformations)
        if not transforms:
            cached_rows_by_word = self._cached_rows_by_word(
                df_cached=df_cached,
                unique_words=unique_words,
            )
            cached_word_set = set(cached_rows_by_word.keys())
            self._emit_progress_event(
                progress_callback,
                "cache_checked",
                cached_words=len(cached_word_set),
                new_words=max(len(unique_words) - len(cached_word_set), 0),
                backfill_words=0,
                total_unique_words=len(unique_words),
                execution_mode="parallel_word_branches",
            )
            self._emit_progress_event(
                progress_callback,
                "pipeline_complete",
                total_duration_seconds=time.perf_counter() - pipeline_started_at,
                output_rows=len(df_original),
                output_columns=list(df_original.columns),
                execution_mode="parallel_word_branches",
            )
            return df_original

        dependencies = self._resolve_word_parallel_dependencies(transforms)
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
        stage_by_index = {
            idx: self._resolve_transform_stage(
                transform=transform,
                llm_transform_types=llm_transform_types,
            )
            for idx, transform in enumerate(transforms)
        }
        cached_rows_by_word = self._cached_rows_by_word(
            df_cached=df_cached,
            unique_words=unique_words,
        )
        cached_word_set = set(cached_rows_by_word.keys())
        new_words_for_cache = [word for word in unique_words if word not in cached_word_set]

        queued_words_by_transform: Dict[int, List[str]] = {
            idx: [] for idx in range(len(transforms))
        }
        running_words_by_transform: Dict[int, List[str]] = {
            idx: [] for idx in range(len(transforms))
        }
        completed_words_by_transform: Dict[int, set[str]] = {
            idx: set() for idx in range(len(transforms))
        }
        transform_word_outputs: Dict[int, Dict[str, Dict[str, Any]]] = {
            idx: {} for idx in range(len(transforms))
        }
        transform_total_durations: Dict[int, float] = {
            idx: 0.0 for idx in range(len(transforms))
        }
        transform_busy: Dict[int, bool] = {idx: False for idx in range(len(transforms))}
        base_df = pd.DataFrame({self.key_field: unique_words})

        for idx, transform in enumerate(transforms):
            for word in unique_words:
                seed_payload = {self.key_field: word}
                cached_row = cached_rows_by_word.get(word)
                if cached_row:
                    seed_payload.update(cached_row)
                    seed_payload[self.key_field] = word
                if self._is_transform_output_complete_for_word(
                    transform=transform,
                    row_payload=seed_payload,
                ):
                    completed_words_by_transform[idx].add(word)
                    transform_word_outputs[idx][word] = seed_payload
                else:
                    queued_words_by_transform[idx].append(word)

        cached_partial_words = [
            word
            for word in unique_words
            if word in cached_word_set
            and any(word in queued_words_by_transform[idx] for idx in range(len(transforms)))
        ]
        main_transform_indexes = [
            idx for idx, stage in stage_by_index.items() if stage != "llm"
        ]
        main_backfill_words_for_cache = [
            word
            for word in unique_words
            if word in cached_word_set
            and any(word in queued_words_by_transform[idx] for idx in main_transform_indexes)
        ]
        cached_complete_words = [
            word for word in unique_words if word in cached_word_set and word not in cached_partial_words
        ]

        self._emit_progress_event(
            progress_callback,
            "cache_checked",
            cached_words=len(cached_word_set),
            new_words=len(new_words_for_cache),
            backfill_words=len(cached_partial_words),
            cached_complete_words=len(cached_complete_words),
            total_unique_words=len(unique_words),
            execution_mode="parallel_word_branches",
        )

        for idx, transform in enumerate(transforms):
            transform_name = type(transform).__name__
            stage = stage_by_index[idx]
            queued_words = queued_words_by_transform[idx]
            self._emit_progress_event(
                progress_callback,
                "transform_queue",
                stage=stage,
                transform_name=transform_name,
                input_rows=len(unique_words),
                current_word=queued_words[0] if queued_words else "",
                words_left=len(queued_words),
                running_words=[],
                queued_words=list(queued_words),
                running_count=0,
                queued_count=len(queued_words),
                execution_mode="parallel_word_branches",
            )
            transform_finished = len(completed_words_by_transform[idx]) >= len(unique_words)
            if transform_finished:
                sample_payload = next(
                    iter(transform_word_outputs[idx].values()),
                    {self.key_field: ""},
                )
                self._emit_progress_event(
                    progress_callback,
                    "transform_complete",
                    stage=stage,
                    transform_name=transform_name,
                    duration_seconds=0.0,
                    output_rows=len(unique_words),
                    output_columns=list(sample_payload.keys()),
                    current_word="",
                    words_left=0,
                    running_words=[],
                    queued_words=[],
                    running_count=0,
                    queued_count=0,
                    step_complete=True,
                    transform_total_duration_seconds=0.0,
                    cached_skip=True,
                    execution_mode="parallel_word_branches",
                )

        in_flight: Dict[Any, tuple[int, str, str, str, float, pd.DataFrame]] = {}

        def _word_dependencies_ready(transform_index: int, word: str) -> bool:
            required_indexes = dependencies.get(transform_index, set())
            return all(
                word in completed_words_by_transform.get(required_index, set())
                for required_index in required_indexes
            )

        def _submit_ready_word_tasks(executor: ThreadPoolExecutor) -> bool:
            submitted_any = False
            for idx, transform in enumerate(transforms):
                if transform_busy[idx]:
                    continue

                queued_words = queued_words_by_transform[idx]
                if not queued_words:
                    continue

                ready_word = next(
                    (word for word in queued_words if _word_dependencies_ready(idx, word)),
                    None,
                )
                if ready_word is None:
                    continue

                queued_words.remove(ready_word)
                running_words = running_words_by_transform[idx]
                running_words.append(ready_word)
                dependency_indexes = dependencies.get(idx, set())
                input_df = self._build_parallel_word_input(
                    word=ready_word,
                    dependency_indexes=dependency_indexes,
                    transform_word_outputs=transform_word_outputs,
                )
                transform_name = type(transform).__name__
                stage = stage_by_index[idx]
                transform_busy[idx] = True

                self._emit_progress_event(
                    progress_callback,
                    "transform_start",
                    stage=stage,
                    transform_name=transform_name,
                    input_rows=len(input_df),
                    current_word=ready_word,
                    words_left=len(queued_words),
                    running_words=list(running_words),
                    queued_words=list(queued_words),
                    running_count=len(running_words),
                    queued_count=len(queued_words),
                    execution_mode="parallel_word_branches",
                )

                started_at = time.perf_counter()
                future = executor.submit(
                    self._apply_llm_transform,
                    transform,
                    input_df,
                )
                in_flight[future] = (
                    idx,
                    ready_word,
                    transform_name,
                    stage,
                    started_at,
                    input_df,
                )
                submitted_any = True
            return submitted_any

        max_workers = max(1, min(len(transforms), 4))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            _submit_ready_word_tasks(executor)
            while any(queued_words_by_transform[idx] for idx in range(len(transforms))) or in_flight:
                if not in_flight:
                    if not _submit_ready_word_tasks(executor):
                        blocked = {
                            type(transforms[idx]).__name__: list(queued_words_by_transform[idx])
                            for idx in range(len(transforms))
                            if queued_words_by_transform[idx]
                        }
                        raise RuntimeError(
                            "Parallel word scheduler is blocked by unresolved dependencies. "
                            f"Blocked queues: {blocked}"
                        )

                completed_futures, _ = wait(
                    list(in_flight.keys()),
                    return_when=FIRST_COMPLETED,
                )
                for future in completed_futures:
                    (
                        idx,
                        completed_word,
                        transform_name,
                        stage,
                        started_at,
                        input_df,
                    ) = in_flight.pop(future)
                    duration_seconds = time.perf_counter() - started_at
                    running_words = running_words_by_transform[idx]
                    if completed_word in running_words:
                        running_words.remove(completed_word)
                    transform_busy[idx] = False
                    queued_words = queued_words_by_transform[idx]

                    try:
                        output_df, _new_columns, measured_duration = future.result()
                        duration_seconds = measured_duration
                        transform_total_durations[idx] += duration_seconds
                        word_output = self._extract_parallel_word_output(
                            word=completed_word,
                            output_df=output_df,
                            fallback_df=input_df,
                        )
                        transform_word_outputs[idx][completed_word] = word_output
                        completed_words_by_transform[idx].add(completed_word)
                        transform_finished = (
                            len(completed_words_by_transform[idx]) >= len(unique_words)
                        )
                        self._emit_progress_event(
                            progress_callback,
                            "transform_complete",
                            stage=stage,
                            transform_name=transform_name,
                            duration_seconds=duration_seconds,
                            output_rows=len(output_df),
                            output_columns=list(output_df.columns),
                            current_word=completed_word,
                            words_left=len(queued_words),
                            running_words=list(running_words),
                            queued_words=list(queued_words),
                            running_count=len(running_words),
                            queued_count=len(queued_words),
                            step_complete=transform_finished,
                            transform_total_duration_seconds=(
                                transform_total_durations[idx] if transform_finished else None
                            ),
                            execution_mode="parallel_word_branches",
                        )
                    except Exception as exc:
                        self._emit_progress_event(
                            progress_callback,
                            "transform_complete",
                            stage=stage,
                            transform_name=transform_name,
                            duration_seconds=duration_seconds,
                            output_rows=len(input_df),
                            output_columns=list(input_df.columns),
                            current_word=completed_word,
                            words_left=len(queued_words),
                            running_words=list(running_words),
                            queued_words=list(queued_words),
                            running_count=len(running_words),
                            queued_count=len(queued_words),
                            error=str(exc),
                            execution_mode="parallel_word_branches",
                        )
                        raise RuntimeError(
                            f"{transform_name} failed in parallel pipeline mode: {exc}"
                        ) from exc

                _submit_ready_word_tasks(executor)

        df_processed = base_df.copy()
        for idx in range(len(transforms)):
            word_outputs = transform_word_outputs.get(idx, {})
            if not word_outputs:
                continue
            output_df = pd.DataFrame(list(word_outputs.values()))
            if self.key_field not in output_df.columns:
                output_df[self.key_field] = list(word_outputs.keys())
            df_processed = self._merge_llm_output(df_processed, output_df)

        df_final = self._merge_with_original_input(
            df_original=df_original,
            df_processed=df_processed,
        )
        self._persist_parallel_main_cache(
            df_final=df_final,
            new_words=new_words_for_cache,
            backfill_words=main_backfill_words_for_cache,
        )
        self._emit_progress_event(
            progress_callback,
            "pipeline_complete",
            total_duration_seconds=time.perf_counter() - pipeline_started_at,
            output_rows=len(df_final),
            output_columns=list(df_final.columns),
            execution_mode="parallel_word_branches",
        )
        return df_final

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
        execution_mode: str = "default",
    ) -> pd.DataFrame:
        """
        Transforms a list of words and optionally emits progress events.
        """
        resolved_mode = str(execution_mode or "default").strip().lower()
        if resolved_mode == "parallel_word_branches":
            return self._transform_data_with_parallel_word_branches(
                words=words,
                dev_mode=dev_mode,
                progress_callback=progress_callback,
            )

        pipeline_started_at = time.perf_counter()
        logger.info(f"Starting pipeline for {len(words)} words...")
        self._emit_progress_event(
            progress_callback,
            "pipeline_start",
            total_words=len(words),
            execution_mode="default",
        )
        if dev_mode:
            words = words[:20]
            logger.warning(f"DEV MODE enabled. Processing only {len(words)} words.")
            self._emit_progress_event(
                progress_callback,
                "dev_mode_applied",
                total_words=len(words),
                execution_mode="default",
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
            execution_mode="default",
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
            execution_mode="default",
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
