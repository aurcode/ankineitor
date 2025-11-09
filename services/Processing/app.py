import streamlit as st
import pandas as pd
import os
from io import StringIO, BytesIO

# --- Core Pipeline Imports ---
# These are your existing python files
from pipeline import TransformationPipeline
from transformations import (
    Transformation,
    PinyinTransformation,
    TranslationTransformation,
    AudioTransformation,
    TimestampTransformation,
)
from llm_transformation import LLMTransformation
from db_client import SQLAlchemyClient
from audio_creator import AudioCreator

# --- Util Imports ---
# This is the modified DataUtils
from data_utils import DataFrameUtils
from loguru import logger

# --- App Configuration ---
st.set_page_config(
    page_title="Ankineitor Control Panel",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Logging Setup ---
# Ensure logs directory exists
os.makedirs("logs", exist_ok=True)
logger.add("logs/streamlit_app.log", rotation="10 MB", level="INFO")


# --- Cached Resource Initialization ---
# Use cache_resource to init dbs and heavy objects once
@st.cache_resource
def get_dependencies():
    """
    Initializes and caches database clients and audio creator.
    This function runs only once.
    """
    logger.info("Initializing dependencies (DBs, AudioCreator)...")
    try:
        pipeline_db = SQLAlchemyClient(db_path="ankineitor_pipeline.db")
        llm_db = SQLAlchemyClient(db_path="ankineitor_llm_cache.db")
        audio_creator = AudioCreator(folder_name="./my_audio_files")

        # We must initialize all possible transformations here
        # so they can be selected in the UI
        all_transforms = {
            "Pinyin": PinyinTransformation(),
            "Translation (to ES)": TranslationTransformation(
                lan_in="zh-CN", lan_out="es"
            ),
            "Audio": AudioTransformation(audio_creator=audio_creator),
            "Timestamp": TimestampTransformation(),
            "LLM (Meanings/Sentences)": LLMTransformation(db_client=llm_db),
        }
        logger.info("Dependencies initialized successfully.")
        return pipeline_db, all_transforms
    except Exception as e:
        logger.critical(f"Failed to initialize dependencies: {e}")
        st.error(
            f"Fatal Error: Could not initialize dependencies. Check logs. Error: {e}"
        )
        return None, None


pipeline_db_client, all_transformations = get_dependencies()

# --- Main App ---
st.title("Ankineitor Control Panel ⚙️")

if not pipeline_db_client or not all_transformations:
    st.error("Application cannot start. Dependencies failed to load.")
else:
    # Create the two main tabs
    tab1, tab2 = st.tabs(["🚀 Run Pipeline", "📊 Merge CSVs"])

    # --- Tab 1: Run Pipeline ---
    with tab1:
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
            )

        st.divider()

        if st.button("🚀 Run Pipeline", type="primary", use_container_width=True):
            if not selected_transforms:
                st.warning("Please select at least one transformation.")
            elif not word_input:
                st.warning("Please input at least one word.")
            else:
                try:
                    # Parse words from text area
                    words_to_process = [
                        word.strip() for word in word_input.split("\n") if word.strip()
                    ]

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
                    st.dataframe(df_results)

                    # Provide download button
                    csv = df_results.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        label="Download results as CSV",
                        data=csv,
                        file_name="pipeline_results.csv",
                        mime="text/csv",
                    )

                except Exception as e:
                    logger.error(f"Error during pipeline run: {e}")
                    st.error(f"An error occurred: {e}")

    # --- Tab 2: Merge CSVs ---
    with tab2:
        st.header("Merge CSVs with Frequency Sum")
        st.markdown(
            """
            Upload two or more CSV files. This tool will merge them and 
            sum the 'frequency' column based on the key columns you provide.
            """
        )

        uploaded_files = st.file_uploader(
            "Upload CSV files", type=["csv"], accept_multiple_files=True
        )

        if uploaded_files:
            if len(uploaded_files) < 2:
                st.info("Please upload at least two CSV files to merge.")
            else:
                dfs = []
                for file in uploaded_files:
                    try:
                        df = pd.read_csv(file)
                        dfs.append(df)
                        st.write(f"Loaded `{file.name}` (Rows: {len(df)})")
                    except Exception as e:
                        st.error(f"Error reading `{file.name}`: {e}")

                if len(dfs) > 1:
                    st.divider()
                    key_columns_input = st.text_input(
                        "Enter key columns (comma-separated)", "word,part"
                    )
                    key_columns = [
                        col.strip()
                        for col in key_columns_input.split(",")
                        if col.strip()
                    ]

                    if st.button(
                        "📊 Merge Files", type="primary", use_container_width=True
                    ):
                        if not key_columns:
                            st.warning("Please provide key columns for merging.")
                        else:
                            try:
                                with st.spinner("Merging and summing frequencies..."):
                                    # Use the logic from your DataUtils
                                    combined_df = DataFrameUtils.combine_dataframes_sum_frequencies(
                                        dfs, key_columns
                                    )

                                st.success("Files merged successfully!")
                                st.dataframe(combined_df)

                                # Provide download button
                                csv = combined_df.to_csv(index=False).encode("utf-8")
                                st.download_button(
                                    label="Download merged CSV",
                                    data=csv,
                                    file_name="merged_frequencies.csv",
                                    mime="text/csv",
                                )
                            except Exception as e:
                                logger.error(f"Error merging CSVs: {e}")
                                st.error(f"An error occurred during merge: {e}")
