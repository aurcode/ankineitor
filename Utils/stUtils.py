import streamlit as st
import pandas as pd

class stUtils:
    def __init__(self) -> None:
        pass

    def print_DF(self, df: pd.DataFrame, title: str = None):
        if title:
            st.title(title)
        st.write(df)

    def request_files(self):
        # Request multiple file uploads
        uploaded_files = st.file_uploader("Choose PDF or PPT files", type=["pdf", "pptx"], accept_multiple_files=True)

        if uploaded_files:
            file_names = [uploaded_file.name for uploaded_file in uploaded_files]
            st.write(file_names)  # Display file names
            return uploaded_files, file_names

        return None, []