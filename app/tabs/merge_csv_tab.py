import streamlit as st
import pandas as pd
from loguru import logger

# Import only the data utils
from ankineitor.common.data_utils import DataFrameUtils


def render_merge_csv_tab():
    """
    Renders the 'Merge CSVs' tab.
    This tab is self-contained and doesn't need injected dependencies.
    """
    st.header("Merge CSVs with Frequency Sum")
    st.markdown(
        """
        Upload two or more CSV files. This tool will merge them and 
        sum the 'frequency' column based on the key columns you provide.
        """
    )

    uploaded_files = st.file_uploader(
        "Upload CSV files",
        type=["csv"],
        accept_multiple_files=True,
        key="csv_merger_uploader",  # Unique key
    )

    if uploaded_files:
        if len(uploaded_files) < 2:
            st.info("Please upload at least two CSV files to merge.")
        else:
            dfs = []
            for file in uploaded_files:
                try:
                    # Set low_memory=False to avoid mixed type warnings
                    df = pd.read_csv(file, low_memory=False)
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
                    col.strip() for col in key_columns_input.split(",") if col.strip()
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
                                combined_df = (
                                    DataFrameUtils.combine_dataframes_sum_frequencies(
                                        dfs, key_columns
                                    )
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
