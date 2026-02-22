import streamlit as st
import pandas as pd
from pathlib import Path
from loguru import logger

from ankineitor.application import (
    PIPELINE_SESSION_KEYS,
    PipelineProgressTracker,
    PipelineRunService,
    PipelineTabStateService,
)
from ankineitor.pipeline.llm_profiles import (
    DEFAULT_LLM_PROFILE_ID,
    get_llm_profile,
    list_llm_profiles,
)
from ankineitor.security import validate_word_input, ValidationError

PROFILE_TRANSFORM_SELECTIONS_KEY = PIPELINE_SESSION_KEYS.profile_transform_selections
SELECTED_TRANSFORM_WIDGET_KEY = PIPELINE_SESSION_KEYS.selected_transform_widget
TRANSFORM_SELECTOR_PROFILE_KEY = PIPELINE_SESSION_KEYS.transform_selector_profile
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


def render_pipeline_tab(pipeline_db_client, all_transformations, transform_factory=None):
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
    llm_profile_options = [profile.profile_id for profile in list_llm_profiles()]
    if not llm_profile_options:
        st.error("No LLM profiles are registered. Configure at least one profile.")
        return

    col1, col2 = st.columns(2)
    pipeline_service = PipelineRunService()
    pipeline_tab_state_service = PipelineTabStateService()
    pipeline_tab_state_service.initialize_session_defaults(st.session_state)

    with col1:
        st.subheader("1. Profile")
        st.caption(
            "Profile controls prompt behavior, source language, and available "
            "transformations."
        )
        default_profile = _coerce_option(
            st.session_state.get("llm_profile_id_ui"),
            llm_profile_options,
            DEFAULT_LLM_PROFILE_ID,
        )
        llm_profile_id = st.selectbox(
            "Profile",
            options=llm_profile_options,
            index=llm_profile_options.index(default_profile),
            format_func=_profile_label,
        )
        selected_profile = get_llm_profile(llm_profile_id)
        llm_source_language = selected_profile.source_language
        st.caption(selected_profile.description)
        st.caption(f"Auto source language: `{llm_source_language}`")
        st.session_state["llm_profile_id_ui"] = llm_profile_id

        transform_options = pipeline_service.resolve_transform_options_for_profile(
            all_transformations=all_transformations,
            selected_profile=selected_profile,
        )
        available_transform_names = transform_options.available_transform_names
        unavailable_transform_reasons = transform_options.unavailable_transform_reasons
        always_included_transform_names = (
            transform_options.always_included_transform_names
        )

        default_selection = pipeline_service.default_transform_selection(
            available_transform_names,
            selected_profile,
        )
        profile_state = pipeline_tab_state_service.resolve_profile_transform_state(
            raw_profile_transform_map=st.session_state.get(
                PROFILE_TRANSFORM_SELECTIONS_KEY
            ),
            valid_profile_ids=llm_profile_options,
            selected_profile_id=llm_profile_id,
            active_selector_profile=st.session_state.get(TRANSFORM_SELECTOR_PROFILE_KEY),
            current_widget_selection=st.session_state.get(
                SELECTED_TRANSFORM_WIDGET_KEY,
                [],
            ),
            available_transform_names=available_transform_names,
            default_selection=default_selection,
        )
        st.session_state[PROFILE_TRANSFORM_SELECTIONS_KEY] = (
            profile_state.profile_transform_map
        )
        st.session_state[SELECTED_TRANSFORM_WIDGET_KEY] = profile_state.widget_selection
        st.session_state[TRANSFORM_SELECTOR_PROFILE_KEY] = (
            profile_state.active_profile_id
        )

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
        st.session_state[PROFILE_TRANSFORM_SELECTIONS_KEY][
            llm_profile_id
        ] = selected_transform_names

        if unavailable_transform_reasons:
            hidden_count = len(unavailable_transform_reasons)
            st.caption(
                f"{hidden_count} transform(s) hidden for this profile."
            )
            with st.expander("Show hidden transformations"):
                for transform_name, reason in unavailable_transform_reasons.items():
                    st.caption(f"`{transform_name}`: {reason}")

        # Build executable transformations: always-included + user-selected optional ones.
        ordered_transform_names = pipeline_service.build_ordered_transform_names(
            all_transformations=all_transformations,
            always_included_transform_names=always_included_transform_names,
            selected_transform_names=selected_transform_names,
        )

    with col2:
        st.subheader("3. Input Words")
        word_input = st.text_area(
            "Enter words (one per line):",
            height=200,
            help="Enter words, one per line. Maximum 1000 words.",
            key=PIPELINE_SESSION_KEYS.word_input,
        )

    st.divider()

    if st.button("🚀 Run Pipeline", type="primary", use_container_width=True):
        selection_error = pipeline_service.validate_transform_run_selection(
            all_transformations=all_transformations,
            ordered_transform_names=ordered_transform_names,
            selected_profile=selected_profile,
        )
        if selection_error:
            st.warning(selection_error)
        elif not word_input:
            st.warning("Please input at least one word.")
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
                    prepared_run = pipeline_service.prepare_pipeline_run(
                        pipeline_db_client=pipeline_db_client,
                        all_transformations=all_transformations,
                        ordered_transform_names=ordered_transform_names,
                        llm_profile_id=llm_profile_id,
                        llm_source_language=llm_source_language,
                        transform_factory=transform_factory,
                        table_name="hanzi_processing",
                    )
                    pipeline = prepared_run.pipeline
                    total_transform_steps = max(
                        1,
                        len(pipeline.main_transformations)
                        + len(pipeline.llm_transformations),
                    )
                    progress_tracker = PipelineProgressTracker(
                        total_transform_steps=total_transform_steps
                    )

                    progress_header = st.empty()
                    progress_status = st.empty()
                    progress_bar = st.progress(0.0)
                    timing_table_placeholder = st.empty()

                    def on_pipeline_progress(event):
                        progress_snapshot = progress_tracker.consume_event(event)
                        if progress_snapshot.header_status == "success":
                            progress_header.success(progress_snapshot.header_text or "")
                        elif progress_snapshot.header_status == "info":
                            progress_header.info(progress_snapshot.header_text or "")

                        if progress_snapshot.status_text:
                            progress_status.caption(progress_snapshot.status_text)

                        progress_bar.progress(progress_snapshot.progress_ratio)
                        if progress_snapshot.step_timings:
                            timing_table_placeholder.dataframe(
                                pd.DataFrame(progress_snapshot.step_timings),
                                use_container_width=True,
                                hide_index=True,
                            )

                    run_result = pipeline_service.execute_pipeline_run(
                        prepared_run=prepared_run,
                        words=words_to_process,
                        llm_profile_id=llm_profile_id,
                        progress_callback=on_pipeline_progress,
                        dev_mode=False,
                    )
                    df_results = run_result.df_results
                    slowest_steps = progress_tracker.slowest_steps(limit=3)
                    if slowest_steps:
                        st.markdown("**Slowest steps**")
                        st.dataframe(
                            pd.DataFrame(slowest_steps),
                            use_container_width=True,
                            hide_index=True,
                        )

                saved_results_csv = run_result.saved_results_csv
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
            key=PIPELINE_SESSION_KEYS.category_name,
        )

        if st.button("Add Category to DB", use_container_width=True):
            try:
                normalized_category = pipeline_service.normalize_category_name(
                    category_name
                )
                with st.spinner(f"Adding category '{normalized_category}'..."):
                    df_categorized = pipeline_service.add_category_to_results(
                        pipeline_db_client=pipeline_db_client,
                        df_results=df_results,
                        category=normalized_category,
                        table_name="hanzi_processing",
                    )

                st.success(
                    f"Category '{normalized_category}' added to {len(df_categorized)} words!"
                )

                # Update the dataframe in the UI and state
                st.session_state.df_results = df_categorized
                st.session_state["app_active_tab"] = "🚀 Run Pipeline"
                st.rerun()

            except ValueError as e:
                st.warning(str(e))
            except Exception as e:
                logger.error(f"Error adding category: {e}")
                st.error(f"An error occurred while adding category: {e}")
