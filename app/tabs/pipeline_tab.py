import streamlit as st
import pandas as pd
import re
from pathlib import Path
from loguru import logger

# Import only the pipeline-specific dependencies
from ankineitor.pipeline import TransformationPipeline
from ankineitor.pipeline.transformations import PinyinTransformation, AudioTransformation
from ankineitor.pipeline.llm_transformation import LLMTransformation
from ankineitor.pipeline.llm_audio_transformation import LLMAudioTransformation
from ankineitor.pipeline.llm_image_prompt_transformation import (
    LLMImagePromptTransformation,
)
from ankineitor.pipeline.llm_image_transformation import LLMImageTransformation
from ankineitor.pipeline.llm_profiles import (
    DEFAULT_LLM_PROFILE_ID,
    get_llm_profile,
    list_llm_profiles,
)
from ankineitor.security import validate_word_input, ValidationError

SOURCE_LANGUAGE_OPTIONS = [
    "English",
    "Spanish",
    "French",
    "German",
    "Portuguese",
    "Italian",
    "Chinese (Simplified)",
    "Japanese",
    "Korean",
    "Hindi",
    "Arabic",
    "Russian",
    "Turkish",
    "Vietnamese",
    "Indonesian",
]
LLM_PROFILE_OPTIONS = [profile.profile_id for profile in list_llm_profiles()]


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


def _language_label(value):
    if value is None:
        return "None"
    return value


def _profile_label(profile_id: str) -> str:
    profile = get_llm_profile(profile_id)
    return profile.display_name


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
    transform_names = list(all_transformations.keys())

    # Persist core pipeline inputs across reruns.
    if "pipeline_selected_transform_names" not in st.session_state:
        default_selected = [
            name
            for name in transform_names
            if name != "Translation (Legacy Google/CEDICT)"
        ]
        st.session_state["pipeline_selected_transform_names"] = (
            default_selected if default_selected else transform_names.copy()
        )
    else:
        st.session_state["pipeline_selected_transform_names"] = [
            name
            for name in st.session_state["pipeline_selected_transform_names"]
            if name in transform_names
        ]
        if not st.session_state["pipeline_selected_transform_names"]:
            st.session_state["pipeline_selected_transform_names"] = transform_names.copy()

    if "pipeline_word_input" not in st.session_state:
        st.session_state["pipeline_word_input"] = "你好\n谢谢\n熊猫\n数据"

    if "pipeline_category_name" not in st.session_state:
        st.session_state["pipeline_category_name"] = ""

    with col1:
        st.subheader("1. Select Transformations")
        selected_transform_names = st.multiselect(
            "Choose transformations to run:",
            options=transform_names,
            key="pipeline_selected_transform_names",
        )

        # Build the list of Transformation objects
        selected_transforms = [
            all_transformations[name] for name in selected_transform_names
        ]

        has_source_language_transform = any(
            isinstance(
                all_transformations[name],
                (PinyinTransformation, AudioTransformation, LLMTransformation, LLMAudioTransformation),
            )
            for name in selected_transform_names
        )
        has_llm_text_transform = any(
            isinstance(all_transformations[name], LLMTransformation)
            for name in selected_transform_names
        )
        llm_source_language = "Chinese (Simplified)"
        llm_profile_id = DEFAULT_LLM_PROFILE_ID

        if has_source_language_transform:
            st.subheader("Source Language")
            st.caption(
                "Default source language is Chinese (Simplified). "
                "If you choose another source language, pinyin is disabled and audio uses that language."
            )

            default_source = _coerce_option(
                st.session_state.get("llm_source_language_ui"),
                SOURCE_LANGUAGE_OPTIONS,
                "Chinese (Simplified)",
            )
            llm_source_language = st.selectbox(
                "Source language",
                options=SOURCE_LANGUAGE_OPTIONS,
                index=SOURCE_LANGUAGE_OPTIONS.index(default_source),
                format_func=_language_label,
            )
            st.session_state["llm_source_language_ui"] = llm_source_language

        if has_llm_text_transform:
            st.subheader("LLM Profile")
            st.caption(
                "Select a profile that defines the full prompt and output structure "
                "for LLM text generation."
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
            st.caption(selected_profile.description)
            st.session_state["llm_profile_id_ui"] = llm_profile_id

    with col2:
        st.subheader("2. Input Words")
        word_input = st.text_area(
            "Enter words (one per line):",
            height=200,
            help="Enter words, one per line. Maximum 1000 words.",
            key="pipeline_word_input",
        )

    st.divider()

    if st.button("🚀 Run Pipeline", type="primary", use_container_width=True):
        if not selected_transforms:
            st.warning("Please select at least one transformation.")
        elif not word_input:
            st.warning("Please input at least one word.")
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

                st.success("Pipeline run complete!")

                # Store results in session state to add category
                st.session_state.df_results = df_results

            except ValidationError as e:
                logger.error(f"Validation error during pipeline run: {e}")
                st.error(f"Input validation error: {e}")
                if "df_results" in st.session_state:
                    del st.session_state.df_results
            except Exception as e:
                logger.error(f"Error during pipeline run: {e}")
                st.error(f"An error occurred: {e}")
                if "df_results" in st.session_state:
                    del st.session_state.df_results

    # Display results and category section if results exist in state
    if "df_results" in st.session_state and not st.session_state.df_results.empty:
        df_results = st.session_state.df_results

        st.subheader("Results")
        st.dataframe(df_results)
        _render_image_prompt_details(df_results)
        _render_image_preview(df_results)

        # Provide download button
        csv = df_results.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label="Download results as CSV",
            data=csv,
            file_name="pipeline_results.csv",
            mime="text/csv",
            key="download_button",
        )

        # Add Category Section
        st.divider()
        st.subheader("3. (Optional) Add Category")
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
