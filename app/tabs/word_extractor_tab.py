import streamlit as st
import pandas as pd
from typing import Dict, List

from ankineitor.pipeline.text_extractor import TextExtractor
from ankineitor.common.data_utils import DataUtils


@st.cache_data
def load_hsk_filters():
    """
    Loads HSK data from remote URLs with the correct parsing rules.
    This is cached to prevent re-downloading on every interaction.
    """
    try:
        # For HSK 1-4, the files are TSV
        columns = ["hanzi", "tradicional", "pinyin1", "pinyin2", "space", "mean"]
        filters = {
            "hsk1": pd.read_csv(
                "https://raw.githubusercontent.com/aurcode/chinese-words/main/Chinese__HSK-1.txt",
                sep="\t",
                names=columns,
            ),
            "hsk2": pd.read_csv(
                "https://raw.githubusercontent.com/aurcode/chinese-words/main/Chinese__HSK-2.txt",
                sep="\t",
                names=columns,
            ),
            "hsk3": pd.read_csv(
                "https://raw.githubusercontent.com/aurcode/chinese-words/main/Chinese__HSK-3.txt",
                sep="\t",
                names=columns,
            ),
            "hsk4": pd.read_csv(
                "https://raw.githubusercontent.com/aurcode/chinese-words/main/Chinese__HSK-4.txt",
                sep="\t",
                names=columns,
            ),
        }

        # For HSK 5, the files are CSV with a semicolon separator
        df_ting = pd.read_csv(
            "https://raw.githubusercontent.com/aurcode/chinese-words/main/hsk-5-vocabulary.csv",
            sep=";",
        )
        df_hsk5 = pd.read_csv(
            "https://raw.githubusercontent.com/aurcode/chinese-words/main/%E5%90%AC%E5%8A%9B-hsk5-vocabulary",
            sep=";",
        )
        # Combine the two HSK5 files
        filters["hsk5"] = (
            pd.concat([df_ting, df_hsk5])
            .drop_duplicates(subset=["hanzi"])
            .reset_index(drop=True)
        )
        return filters
    except Exception as e:
        st.error(f"Failed to load HSK data from GitHub: {e}")
        return None


def word_extractor_tab():
    """
    Streamlit tab for extracting, filtering, and displaying Chinese words from documents.
    """
    st.title("🔠 Word Extractor")

    # --- Session State Initialization ---
    if "word_df" not in st.session_state:
        st.session_state.word_df = pd.DataFrame()
    if "filtered_df" not in st.session_state:
        st.session_state.filtered_df = pd.DataFrame()
    if "excluded_df" not in st.session_state:
        st.session_state.excluded_df = pd.DataFrame()
    if "final_df" not in st.session_state:
        st.session_state.final_df = pd.DataFrame()

    # --- 1. Input Section ---
    st.header("1. Provide Your Text")
    st.write(
        "Upload one or more files (PDF, DOCX, TXT, PPTX) or paste text directly below."
    )

    uploaded_files = st.file_uploader(
        "Upload Documents",
        type=["pdf", "docx", "txt", "pptx"],
        accept_multiple_files=True,
    )
    text_input = st.text_area("Or Paste Text Here", height=200)

    # --- 2. Processing and Filtering ---
    st.header("2. Analyze and Filter")

    if st.button("Analyze Text", type="primary"):
        with st.spinner("Extracting and analyzing text... This may take a moment."):
            # Reset state on new analysis
            st.session_state.word_df = pd.DataFrame()
            st.session_state.filtered_df = pd.DataFrame()
            st.session_state.excluded_df = pd.DataFrame()
            st.session_state.final_df = pd.DataFrame()

            files_to_process: Dict[str, bytes] = {}
            if uploaded_files:
                for up_file in uploaded_files:
                    files_to_process[up_file.name] = up_file.getvalue()
            elif text_input:
                files_to_process["pasted_text.txt"] = text_input.encode("utf-8")

            if files_to_process:
                try:
                    # Initialize and run the extractor
                    extractor = TextExtractor(files_to_process)
                    extractor.extract_content()
                    df = extractor.separated_chinese_characters()

                    if not df.empty:
                        st.session_state.word_df = df
                        st.success(
                            f"✅ Analysis complete! Found {len(df)} unique words."
                        )
                    else:
                        st.warning("No Chinese words were found in the provided text.")

                except Exception as e:
                    st.error(f"An error occurred during analysis: {e}")
            else:
                st.warning("Please upload a file or paste some text to analyze.")

    # --- Display Initial Results ---
    if not st.session_state.word_df.empty:
        st.subheader("Initial Word Frequency")
        st.dataframe(st.session_state.word_df)

        # --- HSK Filtering Section (Corrected Logic) ---
        hsk_data = load_hsk_filters()
        if hsk_data:
            st.subheader("HSK Level Filter")
            st.write("Select HSK levels to **remove** from the list.")
            hsk_levels = list(hsk_data.keys())

            selected_hsk_levels = st.multiselect(
                "Remove words from these HSK levels:",
                options=hsk_levels,
                format_func=lambda x: x.upper(),
            )

            if selected_hsk_levels:
                filters_to_apply = {
                    level: hsk_data[level] for level in selected_hsk_levels
                }

                # The filter_dataframe function returns (excluded, filtered)
                # 'excluded_df' contains words NOT in the HSK lists (the ones we keep).
                # 'filtered_df' contains words that ARE in the HSK lists (the ones removed).
                remaining_df, removed_df = DataUtils.filter_dataframe(
                    st.session_state.word_df,
                    filters_to_apply,
                    filter_column_name="word",
                )
                st.session_state.filtered_df = remaining_df
                st.session_state.excluded_df = removed_df
                st.info(f"Removed {len(removed_df)} words based on HSK filter.")
            else:
                # If no HSK filter is applied, the filtered_df is the same as the original
                st.session_state.filtered_df = st.session_state.word_df
                st.session_state.excluded_df = pd.DataFrame()

            if not st.session_state.filtered_df.empty:
                st.subheader("Words After HSK Filtering")
                st.dataframe(st.session_state.filtered_df)

                # --- Frequency Filtering Section ---
                st.subheader("Frequency Filter")
                min_frequency = st.number_input(
                    "Show words with frequency greater than or equal to:",
                    min_value=1,
                    value=2,
                    step=1,
                )

                final_df = st.session_state.filtered_df[
                    st.session_state.filtered_df["frequency"] >= min_frequency
                ]
                st.session_state.final_df = final_df

                # --- 3. Output Section ---
                st.header("3. Final Word List")
                if not st.session_state.final_df.empty:
                    st.success(
                        f"Displaying {len(st.session_state.final_df)} final words."
                    )

                    # Format for easy copy-pasting
                    word_list_str = "\n".join(
                        st.session_state.final_df["word"].tolist()
                    )
                    st.text_area("Copyable Word List", value=word_list_str, height=300)

                    with st.expander("View Final DataFrame"):
                        st.dataframe(st.session_state.final_df)

                    if not st.session_state.excluded_df.empty:
                        with st.expander("View Words Removed by HSK Filter"):
                            st.dataframe(st.session_state.excluded_df)
                else:
                    st.warning("No words match the current frequency filter.")
        else:
            st.warning(
                "Could not load HSK filter data. Please check your internet connection."
            )
