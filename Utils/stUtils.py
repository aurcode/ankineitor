import streamlit as st
import pandas as pd
from Ankineitor import CHINESE, RECOGNITION, PHOTO_PHOTO_BASIC

class stUtils:
    def __init__(self) -> None:
        self.st = st

    def print_DF(self, df: pd.DataFrame, title: str = None):
        if title:
            self.st.title(title)
        self.st.write(df)

    def request_files(self):
        # Requeself.st multiple file uploads
        uploaded_files = self.st.file_uploader("Choose PDF or PPT files", type=["pdf", "pptx", "txt"], accept_multiple_files=True)

        if uploaded_files:
            file_names = [uploaded_file.name for uploaded_file in uploaded_files]
            self.st.write(file_names)  # Display file names
            return uploaded_files, file_names

        return None, []

    def request_number(self):
        # Requeself.st a number input from the user
        number = self.st.number_input('Input the frequency', min_value=1, max_value=1000, step=1, value=80)

        # Button to confirm the number input
        if self.st.button('Generate'):
            return number

        return None

    def choose_configuration_for_anki(self):
        # Let user choose between two preconfigurations
        config_choice = st.selectbox('Choose configuration:', ['RECOGNITION', 'CHINESE', 'PHOTO_PHOTO_BASIC'])

        if config_choice == 'CHINESE':
            CONFIG = CHINESE
        if config_choice == 'RECOGNITION':
            CONFIG = RECOGNITION
        else:
            CONFIG = PHOTO_PHOTO_BASIC

        st.write(f'You selected: {config_choice}')
        return CONFIG

    def choose_dataframe(self):
        # Let user upload and choose which DataFrame to use
        df_file = st.file_uploader('Upload CSV file for DataFrame', type=['csv'])

        if df_file is not None:
            df = pd.read_csv(df_file)
            st.write('Preview of the uploaded DataFrame:')
            st.write(df)
            #generator = DeckGenerator(df)
            #generator.generate_decks()
            return df

        return None

    def add_separator(self):
        # Add a visual separator using markdown
        st.markdown("<hr>", unsafe_allow_html=True)  # Horizontal rule for separation