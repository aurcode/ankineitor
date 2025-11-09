import streamlit as st
import os
from loguru import logger

# --- Core App Dependencies ---
from db_client import SQLAlchemyClient
from audio_creator import AudioCreator
from transformations import (
    PinyinTransformation,
    TranslationTransformation,
    AudioTransformation,
    TimestampTransformation,
)
from llm_transformation import LLMTransformation

# --- Tab Imports ---
# Import the render functions from their new files
from tabs.pipeline_tab import render_pipeline_tab
from tabs.merge_csv_tab import render_merge_csv_tab

# --- Anki Tab (Mandatory) ---
# We now import this directly. If DeckGenerator or the tab
# file is missing, the app will fail, as expected.
from deck_generator import DeckGenerator
from tabs.anki_tab import render_anki_tab


# --- App Configuration ---
# This MUST be the first Streamlit command
st.set_page_config(
    page_title="Ankineitor Control Panel",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Logging Setup ---
os.makedirs("logs", exist_ok=True)
logger.add("logs/streamlit_app.log", rotation="10 MB", level="INFO")


# --- Cached Resource Initialization ---
@st.cache_resource
def get_dependencies():
    """
    Initializes and caches database clients, audio creator,
    and the list of all available transformations.
    """
    logger.info("Initializing dependencies (DBs, AudioCreator)...")
    try:
        pipeline_db = SQLAlchemyClient(db_path="ankineitor_pipeline.db")
        llm_db = SQLAlchemyClient(db_path="ankineitor_llm_cache.db")
        audio_creator = AudioCreator(folder_name="./my_audio_files")

        # This dictionary holds all possible transformations
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


# --- Main App Execution ---

# Load cached dependencies
pipeline_db_client, all_transformations = get_dependencies()

st.title("Ankineitor Control Panel ⚙️")

if not pipeline_db_client or not all_transformations:
    st.error("Application cannot start. Dependencies failed to load.")
else:
    # --- Tab Creation ---
    # The Anki tab is now mandatory
    tab_list = [
        "🤖Anki Deck Generator",
        "🚀 Run Pipeline",
        "📊 Merge CSVs",
    ]

    tabs = st.tabs(tab_list)

    # --- Render Tab 1 ---
    with tabs[0]:
        render_anki_tab()

    # --- Render Tab 2 ---
    with tabs[1]:
        render_pipeline_tab(pipeline_db_client, all_transformations)

    # --- Render Tab 3 (Mandatory) ---
    with tabs[2]:
        render_merge_csv_tab()
