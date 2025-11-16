import streamlit as st
import pandas as pd
from loguru import logger

# Import only the pipeline-specific dependencies
from ankineitor.pipeline import TransformationPipeline
from ankineitor.security import validate_word_input, ValidationError


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

    with col1:
        st.subheader("1. Select Transformations")
        transform_names = list(all_transformations.keys())
        selected_transform_names = st.multiselect(
            "Choose transformations to run:",
            options=transform_names,
            default=transform_names,  # Default to all
        )

        # Build the list of Transformation objects
        selected_transforms = [
            all_transformations[name] for name in selected_transform_names
        ]

    with col2:
        st.subheader("2. Input Words")
        word_input = st.text_area(
            "Enter words (one per line):",
            "你好\n谢谢\n熊猫\n数据",
            height=200,
            help="Enter Chinese words, one per line. Maximum 1000 words.",
        )

    st.divider()

    if st.button("🚀 Run Pipeline", type="primary", use_container_width=True):
        if not selected_transforms:
            st.warning("Please select at least one transformation.")
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

                    # Initialize the pipeline
                    pipeline = TransformationPipeline(
                        db_client=pipeline_db_client,
                        transformations=selected_transforms,
                        table_name="hanzi_processing",
                    )

                    # Run the pipeline
                    df_results = pipeline.transform_data(
                        words_to_process, dev_mode=False
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
            help="Category name (max 50 characters)"
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
                    st.rerun()

                except Exception as e:
                    logger.error(f"Error adding category: {e}")
                    st.error(f"An error occurred while adding category: {e}")
