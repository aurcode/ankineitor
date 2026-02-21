import streamlit as st
import pandas as pd
import yaml
import re
import tempfile
from pathlib import Path
from loguru import logger

# Import security utilities
from ankineitor.security import (
    validate_file_upload, 
    sanitize_filename,
    ValidationError,
    InvalidFileError
)

# Import templates
from .templates import (
    DEFAULT_MODEL_TEMPLATES_YAML,
    DEFAULT_TAG_RULES_YAML,
    CHINESE_PIPELINE_SETUP
)


def render_anki_tab():
    """
    Renders the 'Anki Deck Generator' tab.
    """
    from deck_generator import DeckGenerator

    st.header("Anki Deck Generator")

    # --- Initialize Session State for Config ---
    if "anki_config" not in st.session_state:
        st.session_state.anki_config = {
            "model_id": 1607392319,
            "model_name": "AURCODE Refactored Model",
            "deck_id": 1234567890,
            "note_type": "Vocabulary",
            # This list defines the Anki fields (no change)
            "model_fields": [
                {"name": "Front"},
                {"name": "Back"},
                {"name": "Example"},
                {"name": "Audio"},
                {"name": "Image"},
                {"name": "Notes"},
            ],
            # UPDATED: This now matches your pipeline output CSV by default
            "model_builder": [
                {"csv_column": "word"},  # Maps to Front
                {"csv_column": "translation"},  # Maps to Back
                {"csv_column": "sentence_1"},  # Maps to Example
                {"csv_column": "audio"},  # Maps to Audio
                {"csv_column": "picture"},  # Maps to Image (a non-existent col is fine)
                {"csv_column": "categories"},  # Maps to Notes
            ],
            # UPDATED: This now matches your pipeline output CSV by default
            "media_fields": [
                {"column_name": "audio", "media_type": "audio"},
                {"column_name": "sentence_1_audio", "media_type": "audio"},
                {"column_name": "sentence_2_audio", "media_type": "audio"},
                {"column_name": "sentence_3_audio", "media_type": "audio"},
                {"column_name": "picture", "media_type": "image"},
            ],
            "model_templates_yaml": DEFAULT_MODEL_TEMPLATES_YAML,
            "tag_rules_yaml": DEFAULT_TAG_RULES_YAML,  # This now uses the new default
        }

    cfg = st.session_state.anki_config

    anki_col1, anki_col2 = st.columns([0.6, 0.4])

    with anki_col1:
        st.subheader("1. Deck Configuration")

        with st.expander("Basics"):
            cfg["model_id"] = st.number_input("Model ID", value=cfg["model_id"], step=1)
            cfg["model_name"] = st.text_input("Model Name", value=cfg["model_name"])
            cfg["deck_id"] = st.number_input("Deck ID", value=cfg["deck_id"], step=1)
            cfg["note_type"] = st.text_input("Note Type", value=cfg["note_type"])

        with st.expander("Field Mapping (CSV -> Anki)"):
            st.markdown(
                "Define Anki fields, then map CSV columns to them. **Order must match!**"
            )
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Anki Model Fields**")
                cfg["model_fields"] = st.data_editor(
                    pd.DataFrame(cfg["model_fields"]), num_rows="dynamic"
                )
            with c2:
                st.markdown("**CSV Column Mapping**")
                cfg["model_builder"] = st.data_editor(
                    pd.DataFrame(cfg["model_builder"]), num_rows="dynamic"
                )

        with st.expander("Media Fields"):
            st.markdown("Define which CSV columns contain media filenames.")
            cfg["media_fields"] = st.data_editor(
                pd.DataFrame(cfg["media_fields"]), num_rows="dynamic"
            )

        with st.expander("Advanced: Templates (YAML)"):
            cfg["model_templates_yaml"] = st.text_area(
                "Model Templates", value=cfg["model_templates_yaml"], height=300
            )

        with st.expander("Advanced: Tag Rules (YAML)"):
            cfg["tag_rules_yaml"] = st.text_area(
                "Tag Rules", value=cfg["tag_rules_yaml"], height=250
            )

    with anki_col2:
        st.subheader("2. Input Data")

        # --- NEW: "Chinese Setup" Button ---
        if st.button(
            "Load 🇨🇳 Chinese Pipeline Setup",
            help="Click to auto-fill all fields for the standard pipeline CSV output",
            use_container_width=True,
        ):
            # Update all config fields in session state
            for key, value in CHINESE_PIPELINE_SETUP.items():
                st.session_state.anki_config[key] = value

            st.success("Loaded Chinese Pipeline setup!")
            st.session_state["app_active_tab"] = "🤖 Anki Deck Generator"
            st.rerun()  # Rerun to reflect changes in all widgets
        # --- End of New Button ---

        uploaded_csv = st.file_uploader(
            "Upload Vocabulary CSV", 
            type=["csv"], 
            key="anki_csv_uploader",
            help="Upload a CSV file with your vocabulary data (max 10MB)"
        )
        deck_name = st.text_input("Deck Name", value="My Anki Deck")
        output_dir = st.text_input("Output Directory", value="output/")

        st.divider()
        st.subheader("3. Generate")

        if st.button(
            "Generate Anki Deck (.apkg)", type="primary", use_container_width=True
        ):
            # --- 1. PRE-VALIDATION ---
            # We will collect all config errors and show them at once.
            errors = []

            # 1a. Check for required file and text inputs
            if not uploaded_csv:
                st.warning("Please upload a vocabulary CSV file.")
                # We return here because we can't validate the CSV-dependent
                # configs below without a file.
                return

            try:
                # Validate file upload
                validate_file_upload(uploaded_csv, expected_extensions=[".csv"])
            except (InvalidFileError, ValidationError) as e:
                st.error(f"File validation error: {e}")
                return

            if not deck_name:
                errors.append("Please provide a 'Deck Name'.")

            if not output_dir:
                errors.append("Please provide an 'Output Directory'.")

            # 1b. Validate YAML parsing
            try:
                model_templates_dict = yaml.safe_load(cfg["model_templates_yaml"])
                if not isinstance(model_templates_dict, dict):
                    errors.append(
                        "'Model Templates' YAML is invalid (must be a dictionary)."
                    )
            except yaml.YAMLError as e:
                errors.append(f"Error parsing 'Model Templates' YAML: {e}")
                model_templates_dict = None

            try:
                tag_rules_list = yaml.safe_load(cfg["tag_rules_yaml"])
                if not isinstance(tag_rules_list, list):
                    errors.append("'Tag Rules' YAML is invalid (must be a list).")
            except yaml.YAMLError as e:
                errors.append(f"Error parsing 'Tag Rules' YAML: {e}")
                tag_rules_list = None

            # 1c. Validate DataFrame-based configs
            model_fields_df = cfg["model_fields"]
            model_builder_df = cfg["model_builder"]
            media_fields_df = cfg["media_fields"]  # OK if this one is empty

            if model_fields_df.empty:
                errors.append("'Anki Model Fields' cannot be empty.")

            if model_builder_df.empty:
                errors.append("'CSV Column Mapping' cannot be empty.")

            # 1d. Check for logic errors (mismatched lengths)
            if not model_fields_df.empty and not model_builder_df.empty:
                if len(model_fields_df) != len(model_builder_df):
                    errors.append(
                        f"Field mismatch: You have {len(model_fields_df)} 'Anki Model Fields' "
                        f"but {len(model_builder_df)} 'CSV Column Mappings'. These must be equal."
                    )

            # --- 2. EXECUTION ---
            # If we found any errors, show them and stop.
            if errors:
                st.error("Please fix the following configuration errors:")
                for err in errors:
                    st.error(f"- {err}")
                return  # Stop execution!

            # If all checks passed, proceed with generation
            try:
                with st.spinner("Generating Anki Deck..."):
                    # 1. Load Data
                    logger.info(f"Reading data from uploaded file: {uploaded_csv.name}")
                    
                    # Sanitize filename
                    safe_filename = sanitize_filename(uploaded_csv.name)
                    logger.info(f"Original filename: {uploaded_csv.name}, Sanitized: {safe_filename}")
                    
                    df = pd.read_csv(uploaded_csv)
                    df = df.astype(object).where(pd.notnull(df), None)  # Replace NaN with None

                    # Validate data
                    if df.empty:
                        st.error("The uploaded CSV file is empty.")
                        return
                    
                    if len(df) > 10000:
                        st.warning(f"Large dataset detected ({len(df)} rows). Processing may take some time.")

                    # 2. Assemble Config (using validated variables)
                    logger.info("Assembling configuration from UI...")
                    config_dict = {
                        "basics": {
                            # Explicitly cast to int to be defensive.
                            # st.number_input can return float (e.g., 123.0)
                            "model_id": int(cfg["model_id"]),
                            "model_name": cfg["model_name"],
                            "deck_id": int(cfg["deck_id"]),
                            "note_type": cfg["note_type"],
                        },
                        "model_fields": model_fields_df.to_dict("records"),
                        "model_builder": model_builder_df["csv_column"].tolist(),
                        "media_fields": media_fields_df.to_dict("records"),
                        "model_templates": model_templates_dict,  # Use parsed dict
                        "tag_rules": tag_rules_list,  # Use parsed list
                    }

                    # 3. Write temp config using a unique file name per run/session
                    with tempfile.NamedTemporaryFile(
                        mode="w",
                        suffix=".yaml",
                        prefix="anki_config_",
                        delete=False,
                        encoding="utf-8",
                    ) as tmp_file:
                        temp_config_file = Path(tmp_file.name)
                        yaml.dump(config_dict, tmp_file, allow_unicode=True)

                    # 4. Ensure output dir exists
                    output_path = Path(output_dir)
                    output_path.mkdir(parents=True, exist_ok=True)

                    # 5. Initialize Generator and Run
                    logger.info("Initializing DeckGenerator...")
                    generator = DeckGenerator(config_path=temp_config_file)

                    logger.info(f"Generating deck '{deck_name}'...")
                    generator.generate_deck(
                        df=df,
                        deck_name=deck_name,
                        output_path=output_path,
                        strict=False,
                    )

                    deck_file_path = output_path / f"{deck_name}.apkg"

                    # 6. Clean up temp file
                    temp_config_file.unlink()

                    if deck_file_path.exists():
                        st.success(f"Deck '{deck_name}.apkg' generated successfully!")
                        # 7. Provide download
                        with open(deck_file_path, "rb") as f:
                            st.download_button(
                                label=f"Download {deck_name}.apkg",
                                data=f.read(),
                                file_name=f"{deck_name}.apkg",
                                mime="application/octet-stream",
                                use_container_width=True,
                            )
                    else:
                        st.error(
                            "Deck generation finished, but no .apkg file was found."
                        )

            except Exception as e:
                # This will still catch the error you saw, but now
                # we know it's not a simple config error.
                logger.critical(f"An error occurred during deck generation: {e}")
                st.error(f"An unexpected error occurred: {e}")
                # Clean up temp file on error too
                if "temp_config_file" in locals() and temp_config_file.exists():
                    temp_config_file.unlink()
