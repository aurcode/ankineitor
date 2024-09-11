import streamlit as st
import pandas as pd
from Ankineitor import CHINESE, RECOGNITION, PHOTO_PHOTO_BASIC
from Utils import DataUtils

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

    def filter_by_category(self, df: pd.DataFrame) -> pd.DataFrame:
        all_categories = DataUtils.get_all_categories()
        selected_category = self.st.selectbox('Choose an existing category or type a new one', options=['']+all_categories, index=0)

        if not selected_category == '':
            return df

        # Create a boolean mask for the filtering condition
        mask = df['categories'].apply(
            lambda x: any(cat.strip() in x.split(', ') for cat in selected_category.split(', '))
        )
        # Filter the DataFrame
        return df[mask]

    def request_category(self):
        # Request the user to input a category or select an existing one
        all_categories = DataUtils.get_all_categories()

        # Show a text input for a new category
        selected_category = self.st.selectbox('Choose an existing category or type a new one', options=all_categories, index=0)

        new_category = self.st.text_input('Or create a new category', value='')

        # Button to confirm the selection or creation of a category
        if self.st.button('SetCategory'):
            if new_category:  # If a new category is provided, use it
                return new_category
            return selected_category  # Otherwise, return the selected category

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