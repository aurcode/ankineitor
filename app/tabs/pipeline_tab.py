import streamlit as st
import pandas as pd
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from loguru import logger

# Import only the pipeline-specific dependencies
from ankineitor.pipeline import TransformationPipeline
from ankineitor.pipeline.transformations import (
    AudioTransformation,
    PinyinTransformation,
    TranslationTransformation,
    TimestampTransformation,
)
from ankineitor.pipeline.llm_transformation import LLMTransformation
from ankineitor.pipeline.llm_image_prompt_transformation import (
    LLMImagePromptTransformation,
)
from ankineitor.pipeline.llm_image_transformation import LLMImageTransformation
from ankineitor.pipeline.llm_audio_transformation import LLMAudioTransformation
from ankineitor.pipeline.llm_profiles import (
    DEFAULT_LLM_PROFILE_ID,
    SP_RUSSIAN_PROFILE_ID,
    get_llm_profile,
    list_llm_profiles,
)
from ankineitor.common.pipeline_result_store import save_pipeline_results_csv
from ankineitor.security import validate_word_input, ValidationError

LLM_PROFILE_OPTIONS = [profile.profile_id for profile in list_llm_profiles()]
PROFILE_TRANSFORM_SELECTIONS_KEY = "pipeline_selected_transform_names_by_profile"
SELECTED_TRANSFORM_WIDGET_KEY = "pipeline_selected_transform_names"
TRANSFORM_SELECTOR_PROFILE_KEY = "pipeline_transform_selector_profile_id"
ALWAYS_AUDIO_PROFILE_IDS = {DEFAULT_LLM_PROFILE_ID, SP_RUSSIAN_PROFILE_ID}
LAST_SAVED_RESULTS_CSV_KEY = "pipeline_last_saved_results_csv"
LAST_RESULTS_PROFILE_KEY = "pipeline_last_results_profile"


def _coerce_option(value, options, fallback):
    """Map persisted/free-text values to one of the allowed options."""
    if value is None:
        return fallback

    value_str = str(value).strip()
    if value_str in options:
        return value_str

    for option in options:
        if option.lower() == value_str.lower():
            return option

    return fallback


def _profile_label(profile_id: str) -> str:
    profile = get_llm_profile(profile_id)
    return profile.display_name


def _get_unavailable_transform_reason(
    transform_name: str,
    transform: object,
    profile_supports_images: bool,
    profile_id: str,
) -> Optional[str]:
    del transform_name
    if isinstance(transform, LLMTransformation):
        return "Always included automatically (core profile prompt stage)."
    if isinstance(transform, TimestampTransformation):
        return "Always included automatically (creation timestamp)."
    if isinstance(transform, PinyinTransformation):
        return "Provided by the profile prompt output."
    if isinstance(transform, TranslationTransformation):
        return "Provided by the profile prompt output."
    if isinstance(transform, AudioTransformation):
        if profile_id in ALWAYS_AUDIO_PROFILE_IDS:
            return "Always included automatically for this profile."
        return "Use the single profile-aware sentence audio transform."
    if (
        isinstance(transform, LLMAudioTransformation)
        and profile_id in ALWAYS_AUDIO_PROFILE_IDS
    ):
        return "Always included automatically for this profile."
    if isinstance(transform, (LLMImagePromptTransformation, LLMImageTransformation)):
        if not profile_supports_images:
            return "Image transforms are disabled for this profile."
    return None


def _resolve_transform_options_for_profile(
    all_transformations: Dict[str, object],
    profile_supports_images: bool,
    profile_id: str,
) -> Tuple[List[str], Dict[str, str], List[str]]:
    available_names: List[str] = []
    unavailable_reasons: Dict[str, str] = {}
    always_included_names: List[str] = []

    for name, transform in all_transformations.items():
        if isinstance(transform, (LLMTransformation, TimestampTransformation)):
            always_included_names.append(name)
        if profile_id in ALWAYS_AUDIO_PROFILE_IDS and isinstance(
            transform, (AudioTransformation, LLMAudioTransformation)
        ):
            always_included_names.append(name)
        reason = _get_unavailable_transform_reason(
            transform_name=name,
            transform=transform,
            profile_supports_images=profile_supports_images,
            profile_id=profile_id,
        )
        if reason:
            unavailable_reasons[name] = reason
        else:
            available_names.append(name)

    return available_names, unavailable_reasons, always_included_names


def _default_transform_selection(
    available_transform_names: List[str],
) -> List[str]:
    del available_transform_names
    return []


def _render_image_preview(df_results: pd.DataFrame) -> None:
    """Render generated image previews from the `picture` column."""
    if "picture" not in df_results.columns:
        return

    image_df = df_results[["word", "picture"]].dropna(subset=["picture"]).copy()
    image_df["picture"] = image_df["picture"].astype(str).str.strip()
    image_df = image_df[image_df["picture"] != ""]

    if image_df.empty:
        st.info("No generated images found in `picture` yet.")
        return

    st.subheader("Generated Image Preview")
    st.caption(f"Showing all {len(image_df)} generated images.")

    columns = st.columns(3)
    missing_count = 0

    for idx, row in image_df.reset_index(drop=True).iterrows():
        word = str(row.get("word", "")).strip() or "(no word)"
        image_path = Path(row["picture"])
        column = columns[idx % len(columns)]

        with column:
            st.markdown(f"**{word}**")
            if image_path.exists():
                st.image(str(image_path), use_container_width=True)
                st.caption(str(image_path))
            else:
                missing_count += 1
                st.warning(f"Missing file: `{image_path}`")

    if missing_count > 0:
        st.warning(
            f"{missing_count} preview item(s) point to files that do not exist locally."
        )


def _render_image_prompt_details(df_results: pd.DataFrame) -> None:
    """Render stage-1 prompt details and skipped-item diagnostics."""
    if "image_generation_skip_reason" in df_results.columns:
        skipped = (
            df_results[["word", "image_generation_skip_reason"]]
            .dropna(subset=["image_generation_skip_reason"])
            .copy()
        )
        skipped["image_generation_skip_reason"] = (
            skipped["image_generation_skip_reason"].astype(str).str.strip()
        )
        skipped = skipped[skipped["image_generation_skip_reason"] != ""]
        if not skipped.empty:
            st.warning(
                f"{len(skipped)} word(s) were skipped by Stage 1 prompt generation."
            )
            st.dataframe(skipped, use_container_width=True, hide_index=True)

    if "master_image_prompt" in df_results.columns:
        preview_columns = [
            "word",
            "image_term_type",
            "visual_description",
            "master_image_prompt",
        ]
        preview_columns = [col for col in preview_columns if col in df_results.columns]
        if len(preview_columns) > 1:
            st.subheader("Stage 1 Prompt Outputs")
            st.dataframe(
                df_results[preview_columns],
                use_container_width=True,
                hide_index=True,
            )


def render_pipeline_tab(pipeline_db_client, all_transformations):
    """
    Renders the 'Run Pipeline' tab.
    Dependencies are injected from the main app.py.
    """
    st.header("Run Word Processing Pipeline")
    st.markdown(
        """
        Select the transformations you want to apply, enter your words, 
        and click 'Run Pipeline'. The system will use the same caching 
        logic as `main.py`.
        """
    )

    col1, col2 = st.columns(2)
    if PROFILE_TRANSFORM_SELECTIONS_KEY not in st.session_state or not isinstance(
        st.session_state.get(PROFILE_TRANSFORM_SELECTIONS_KEY), dict
    ):
        st.session_state[PROFILE_TRANSFORM_SELECTIONS_KEY] = {}

    if "pipeline_word_input" not in st.session_state:
        st.session_state["pipeline_word_input"] = "你好\n谢谢\n熊猫\n数据"

    if "pipeline_category_name" not in st.session_state:
        st.session_state["pipeline_category_name"] = ""

    with col1:
        st.subheader("1. Profile")
        st.caption(
            "Profile controls prompt behavior, source language, and available "
            "transformations."
        )
        default_profile = _coerce_option(
            st.session_state.get("llm_profile_id_ui"),
            LLM_PROFILE_OPTIONS,
            DEFAULT_LLM_PROFILE_ID,
        )
        llm_profile_id = st.selectbox(
            "Profile",
            options=LLM_PROFILE_OPTIONS,
            index=LLM_PROFILE_OPTIONS.index(default_profile),
            format_func=_profile_label,
        )
        selected_profile = get_llm_profile(llm_profile_id)
        llm_source_language = selected_profile.source_language
        st.caption(selected_profile.description)
        st.caption(f"Auto source language: `{llm_source_language}`")
        st.session_state["llm_profile_id_ui"] = llm_profile_id

        (
            available_transform_names,
            unavailable_transform_reasons,
            always_included_transform_names,
        ) = (
            _resolve_transform_options_for_profile(
                all_transformations=all_transformations,
                profile_supports_images=selected_profile.supports_images,
                profile_id=llm_profile_id,
            )
        )

        profile_transform_map: Dict[str, List[str]] = st.session_state[
            PROFILE_TRANSFORM_SELECTIONS_KEY
        ]
        previous_selection = profile_transform_map.get(llm_profile_id)
        if not isinstance(previous_selection, list):
            previous_selection = []

        active_selector_profile = st.session_state.get(TRANSFORM_SELECTOR_PROFILE_KEY)
        current_widget_selection = st.session_state.get(SELECTED_TRANSFORM_WIDGET_KEY, [])
        if not isinstance(current_widget_selection, list):
            current_widget_selection = []

        if active_selector_profile != llm_profile_id:
            selected_for_profile = [
                name for name in previous_selection if name in available_transform_names
            ]
            if not selected_for_profile:
                selected_for_profile = _default_transform_selection(
                    available_transform_names
                )
            st.session_state[SELECTED_TRANSFORM_WIDGET_KEY] = selected_for_profile
            st.session_state[TRANSFORM_SELECTOR_PROFILE_KEY] = llm_profile_id
        else:
            filtered_current = [
                name
                for name in current_widget_selection
                if name in available_transform_names
            ]
            if filtered_current != current_widget_selection:
                st.session_state[SELECTED_TRANSFORM_WIDGET_KEY] = filtered_current

        st.subheader("2. Select Transformations")
        if always_included_transform_names:
            st.caption(
                "Always included: "
                + ", ".join(f"`{name}`" for name in always_included_transform_names)
            )
        st.caption("Select only optional independent transforms (audio/image, etc.).")
        selected_transform_names = st.multiselect(
            "Choose transformations to run:",
            options=available_transform_names,
            key=SELECTED_TRANSFORM_WIDGET_KEY,
        )
        profile_transform_map[llm_profile_id] = selected_transform_names

        if unavailable_transform_reasons:
            hidden_count = len(unavailable_transform_reasons)
            st.caption(
                f"{hidden_count} transform(s) hidden for this profile."
            )
            with st.expander("Show hidden transformations"):
                for transform_name, reason in unavailable_transform_reasons.items():
                    st.caption(f"`{transform_name}`: {reason}")

        # Build executable transformations: always-included + user-selected optional ones.
        ordered_transform_names: List[str] = []
        for name in always_included_transform_names + selected_transform_names:
            if name in all_transformations and name not in ordered_transform_names:
                ordered_transform_names.append(name)
        selected_transforms = [all_transformations[name] for name in ordered_transform_names]

    with col2:
        st.subheader("3. Input Words")
        word_input = st.text_area(
            "Enter words (one per line):",
            height=200,
            help="Enter words, one per line. Maximum 1000 words.",
            key="pipeline_word_input",
        )

    st.divider()

    if st.button("🚀 Run Pipeline", type="primary", use_container_width=True):
        if not selected_transforms:
            st.warning("No runnable transformations are configured.")
        elif not word_input:
            st.warning("Please input at least one word.")
        elif any(
            isinstance(transform, (LLMImagePromptTransformation, LLMImageTransformation))
            for transform in selected_transforms
        ) and not selected_profile.supports_images:
            st.warning(
                f"Profile '{selected_profile.display_name}' does not support image transforms. "
                "Deselect image prompt/renderer for this profile."
            )
        elif any(
            isinstance(transform, LLMImageTransformation)
            for transform in selected_transforms
        ) and not any(
            isinstance(transform, LLMImagePromptTransformation)
            for transform in selected_transforms
        ):
            st.warning(
                "LLM Image Renderer requires LLM Image Prompt (Visual Translator). "
                "Select both stages."
            )
        else:
            try:
                # Validate and sanitize word input
                words_to_process = validate_word_input(word_input)
                
                # Limit processing to prevent abuse
                if len(words_to_process) > 1000:
                    st.warning(f"Limiting processing to first 1000 words (you provided {len(words_to_process)})")
                    words_to_process = words_to_process[:1000]

                with st.spinner(f"Processing {len(words_to_process)} words..."):
                    logger.info(
                        f"Starting pipeline run for {len(words_to_process)} words via Streamlit."
                    )
                    for transform in selected_transforms:
                        if hasattr(transform, "source_language"):
                            transform.source_language = llm_source_language
                        if isinstance(transform, LLMTransformation):
                            transform.profile_id = llm_profile_id
                            transform.profile = get_llm_profile(llm_profile_id)
                        if isinstance(transform, LLMAudioTransformation):
                            transform.profile_id = llm_profile_id

                    # Initialize the pipeline
                    pipeline = TransformationPipeline(
                        db_client=pipeline_db_client,
                        transformations=selected_transforms,
                        table_name="hanzi_processing",
                    )
                    total_transform_steps = max(
                        1,
                        len(pipeline.main_transformations)
                        + len(pipeline.llm_transformations),
                    )
                    steps_completed = 0
                    step_timings = []

                    progress_header = st.empty()
                    progress_status = st.empty()
                    progress_bar = st.progress(0.0)
                    timing_table_placeholder = st.empty()

                    def on_pipeline_progress(event):
                        nonlocal steps_completed

                        event_type = event.get("event")
                        if event_type == "pipeline_start":
                            progress_header.info("Pipeline started.")
                            progress_status.caption(
                                f"Preparing {event.get('total_words', 0)} words..."
                            )
                            progress_bar.progress(0.02)
                            return

                        if event_type == "cache_checked":
                            progress_status.caption(
                                "Cache checked: {cached} cached, {new} new words.".format(
                                    cached=event.get("cached_words", 0),
                                    new=event.get("new_words", 0),
                                )
                            )
                            progress_bar.progress(0.08)
                            return

                        if event_type == "transform_start":
                            progress_status.caption(
                                "Running {stage}: {name}...".format(
                                    stage=event.get("stage", "step").upper(),
                                    name=event.get("transform_name", ""),
                                )
                            )
                            return

                        if event_type == "transform_complete":
                            steps_completed += 1
                            duration_seconds = float(event.get("duration_seconds", 0.0))
                            step_timings.append(
                                {
                                    "stage": event.get("stage", ""),
                                    "step": event.get("transform_name", ""),
                                    "seconds": round(duration_seconds, 2),
                                }
                            )
                            progress_ratio = min(
                                0.95, steps_completed / float(total_transform_steps)
                            )
                            progress_bar.progress(progress_ratio)
                            progress_status.caption(
                                "{name} finished in {seconds:.2f}s".format(
                                    name=event.get("transform_name", ""),
                                    seconds=duration_seconds,
                                )
                            )
                            timing_table_placeholder.dataframe(
                                pd.DataFrame(step_timings),
                                use_container_width=True,
                                hide_index=True,
                            )
                            return

                        if event_type == "pipeline_complete":
                            progress_bar.progress(1.0)
                            progress_header.success("Pipeline complete.")
                            total_duration = float(
                                event.get("total_duration_seconds", 0.0)
                            )
                            progress_status.caption(
                                f"Total duration: {total_duration:.2f}s"
                            )

                    # Run the pipeline
                    df_results = pipeline.transform_data_with_progress(
                        words=words_to_process,
                        dev_mode=False,
                        progress_callback=on_pipeline_progress,
                    )
                    if step_timings:
                        slowest_steps = (
                            pd.DataFrame(step_timings)
                            .sort_values("seconds", ascending=False)
                            .head(3)
                        )
                        st.markdown("**Slowest steps**")
                        st.dataframe(
                            slowest_steps,
                            use_container_width=True,
                            hide_index=True,
                        )

                saved_results_csv = save_pipeline_results_csv(
                    df_results=df_results,
                    profile_id=llm_profile_id,
                )
                st.success("Pipeline run complete!")
                st.info(
                    "Saved results to `{}`".format(saved_results_csv.as_posix())
                )

                # Store results in session state to add category
                st.session_state.df_results = df_results
                st.session_state[LAST_SAVED_RESULTS_CSV_KEY] = saved_results_csv.as_posix()
                st.session_state[LAST_RESULTS_PROFILE_KEY] = llm_profile_id

            except ValidationError as e:
                logger.error(f"Validation error during pipeline run: {e}")
                st.error(f"Input validation error: {e}")
                if "df_results" in st.session_state:
                    del st.session_state.df_results
                st.session_state.pop(LAST_SAVED_RESULTS_CSV_KEY, None)
                st.session_state.pop(LAST_RESULTS_PROFILE_KEY, None)
            except Exception as e:
                logger.error(f"Error during pipeline run: {e}")
                st.error(f"An error occurred: {e}")
                if "df_results" in st.session_state:
                    del st.session_state.df_results
                st.session_state.pop(LAST_SAVED_RESULTS_CSV_KEY, None)
                st.session_state.pop(LAST_RESULTS_PROFILE_KEY, None)

    # Display results and category section if results exist in state
    if "df_results" in st.session_state and not st.session_state.df_results.empty:
        df_results = st.session_state.df_results

        st.subheader("Results")
        st.dataframe(df_results)
        _render_image_prompt_details(df_results)
        _render_image_preview(df_results)

        # Provide download button
        csv = df_results.to_csv(index=False).encode("utf-8-sig")
        last_saved_results_csv = st.session_state.get(LAST_SAVED_RESULTS_CSV_KEY, "")
        download_file_name = "pipeline_results.csv"
        if last_saved_results_csv:
            download_file_name = Path(str(last_saved_results_csv)).name
        st.download_button(
            label="Download results as CSV",
            data=csv,
            file_name=download_file_name,
            mime="text/csv",
            key="download_button",
        )

        # Add Category Section
        st.divider()
        st.subheader("4. (Optional) Add Category")
        st.markdown(
            """
            Add a custom category (like 'HSK1' or 'My List') to all 
            the words you just processed. This will be saved to the database.
            """
        )

        category_name = st.text_input(
            "Enter a category for these words:",
            max_chars=50,
            help="Category name (max 50 characters)",
            key="pipeline_category_name",
        )

        if st.button("Add Category to DB", use_container_width=True):
            if not category_name:
                st.warning("Please enter a category name.")
            elif len(category_name.strip()) < 2:
                st.warning("Category name must be at least 2 characters long.")
            elif not re.match(r'^[a-zA-Z0-9_\-\s]+$', category_name):
                st.warning("Category name contains invalid characters. Use only letters, numbers, spaces, hyphens, and underscores.")
            else:
                try:
                    with st.spinner(f"Adding category '{category_name}'..."):
                        # Re-init pipeline for the .transform_categories method
                        pipeline = TransformationPipeline(
                            db_client=pipeline_db_client,
                            transformations=[],  # No transforms needed
                            table_name="hanzi_processing",
                        )

                        df_categorized = pipeline.transform_categories(
                            df_results, category=category_name.strip()
                        )

                    st.success(
                        f"Category '{category_name}' added to {len(df_categorized)} words!"
                    )

                    # Update the dataframe in the UI and state
                    st.session_state.df_results = df_categorized
                    st.session_state["app_active_tab"] = "🚀 Run Pipeline"
                    st.rerun()

                except Exception as e:
                    logger.error(f"Error adding category: {e}")
                    st.error(f"An error occurred while adding category: {e}")
