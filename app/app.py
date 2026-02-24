import streamlit as st
import os
import inspect
from loguru import logger

# --- Core App Dependencies ---
from ankineitor.pipeline.db_client import SQLAlchemyClient
from ankineitor.pipeline.audio_creator import AudioCreator
from ankineitor.pipeline.transformations import (
    AudioTransformation,
    TimestampTransformation,
)
from ankineitor.pipeline.llm_transformation import LLMTransformation
from ankineitor.pipeline.llm_audio_transformation import LLMAudioTransformation
from ankineitor.pipeline.llm_image_prompt_transformation import (
    LLMImagePromptTransformation,
)
from ankineitor.pipeline.llm_image_transformation import LLMImageTransformation
from ankineitor.pipeline.llm_profiles import DEFAULT_LLM_PROFILE_ID, get_llm_profile

# --- Tab Imports ---
# Import the render functions from their new files
from tabs.pipeline_tab import render_pipeline_tab
from tabs.merge_csv_tab import render_merge_csv_tab
from tabs.csv_flashcards_tab import render_csv_flashcards_tab
from tabs.word_extractor_tab import word_extractor_tab

# --- Anki Tab (Mandatory) ---
# We now import this directly. If DeckGenerator or the tab
# file is missing, the app will fail, as expected.
from tabs.anki_tab import render_anki_tab


# --- App Configuration ---
# This MUST be the first Streamlit command
st.set_page_config(
    page_title="Ankineitor Control Panel",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Logging Setup ---
@st.cache_resource
def setup_logging():
    os.makedirs("logs", exist_ok=True)
    logger.add("logs/streamlit_app.log", rotation="10 MB", level="INFO")


setup_logging()


# --- Cached Resource Initialization ---
@st.cache_resource
def get_dependencies():
    """
    Initializes and caches database clients, audio creator,
    and the list of all available transformations.
    """
    logger.info("Initializing dependencies (DBs, AudioCreator)...")
    try:
        pipeline_db = SQLAlchemyClient(db_path="data/ankineitor_pipeline.db")
        llm_db = SQLAlchemyClient(db_path="data/ankineitor_llm_cache.db")
        audio_creator = AudioCreator(folder_name="./my_audio_files")

        def build_transformations(
            llm_profile_id: str = DEFAULT_LLM_PROFILE_ID,
            llm_source_language: str = "",
        ):
            profile_id = (llm_profile_id or DEFAULT_LLM_PROFILE_ID).strip()
            source_language = (
                llm_source_language
                or get_llm_profile(profile_id).source_language
                or "Chinese (Simplified)"
            )
            # Ordered logically: basic transformations first, then LLM, then sentence audio.
            return {
                "Audio": AudioTransformation(
                    audio_creator=audio_creator,
                    source_language=source_language,
                ),
                "Timestamp": TimestampTransformation(),
                "LLM (Meanings/Sentences)": LLMTransformation(
                    db_client=llm_db,
                    profile_id=profile_id,
                ),
                "LLM Image Prompt (Visual Translator)": LLMImagePromptTransformation(
                    db_client=llm_db,
                    source_language=source_language,
                ),
                "LLM Image Renderer (Master Prompt)": LLMImageTransformation(
                    profile_id=profile_id,
                ),
                "LLM Audio (Sentences)": LLMAudioTransformation(
                    audio_creator=audio_creator,
                    source_language=source_language,
                    profile_id=profile_id,
                ),
            }

        # Keep one preview map for UI selection, but build fresh instances per run.
        all_transforms = build_transformations()
        logger.info("Dependencies initialized successfully.")
        return pipeline_db, all_transforms, build_transformations
    except Exception as e:
        logger.critical(f"Failed to initialize dependencies: {e}")
        st.error(
            f"Fatal Error: Could not initialize dependencies. Check logs. Error: {e}"
        )
        return None, None, None


# --- Main App Execution ---

# Load cached dependencies
pipeline_db_client, all_transformations, transform_factory = get_dependencies()

st.title("Ankineitor Control Panel ⚙️")

if not pipeline_db_client or not all_transformations:
    st.error("Application cannot start. Dependencies failed to load.")
else:
    # Use explicit stateful navigation so reruns keep the same active section.
    tab_list = [
        "🤖 Anki Deck Generator",
        "🚀 Run Pipeline",
        "🃏 Flashcard Reviewer",
        "📊 Merge CSVs",
        "🔠 Word Extractor",
    ]
    if (
        "app_active_tab" not in st.session_state
        or st.session_state["app_active_tab"] not in tab_list
    ):
        st.session_state["app_active_tab"] = tab_list[0]

    radio_kwargs = {
        "label": "Section",
        "options": tab_list,
        "key": "app_active_tab",
    }
    radio_signature = inspect.signature(st.radio).parameters
    if "horizontal" in radio_signature:
        radio_kwargs["horizontal"] = True
    if "label_visibility" in radio_signature:
        radio_kwargs["label_visibility"] = "collapsed"

    selected_tab = st.radio(**radio_kwargs)

    if selected_tab == tab_list[0]:
        render_anki_tab()
    elif selected_tab == tab_list[1]:
        render_pipeline_tab(
            pipeline_db_client,
            all_transformations,
            transform_factory=transform_factory,
        )
    elif selected_tab == tab_list[2]:
        render_csv_flashcards_tab()
    elif selected_tab == tab_list[3]:
        render_merge_csv_tab()
    elif selected_tab == tab_list[4]:
        word_extractor_tab()
