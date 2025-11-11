import streamlit as st
import pandas as pd
import yaml
from pathlib import Path
from loguru import logger

# --- Default Anki Configs (from your example) ---
# This is the "basic" setup
DEFAULT_MODEL_TEMPLATES_YAML = """
main:
  - name: "Card 1"
    qfmt: "{{Front}}<br>{{Image}}"
    afmt: "{{FrontSide}}<hr id=answer>{{Back}}<br><br>{{Example}}{{Audio}}<br><br><i>{{Notes}}</i>"
css: |
  .card {
    font-family: arial;
    font-size: 20px;
    text-align: center;
    color: black;
    background-color: white;
  }
"""

DEFAULT_TAG_RULES_YAML = """
- static_tags:
    - "@AURCODE"
    - "PipelineDeck"
- prefix: "Category"
  # column: "categories" # Matches the CSV column
  split_by: ","
"""

# --- NEW: Full Configuration for the "Chinese Pipeline" Button ---
# This dictionary contains all the settings for your specific CSV
CHINESE_PIPELINE_SETUP = {
    "model_id": 20251110,  # New custom ID for this model
    "model_name": "Chinese Pipeline Model (Full)",
    "deck_id": 20251111,
    "note_type": "Chinese (Pipeline)",
    # 1. Anki Model Fields: All the fields in the Anki note
    "model_fields": [
        {"name": "Word"},  # Front
        {"name": "Pinyin"},
        {"name": "English Meaning"},
        {"name": "Spanish Meaning"},
        {"name": "Audio"},
        {"name": "Example 1"},
        {"name": "Example 2"},
        {"name": "Example 3"},
        {"name": "Translation (Extras)"},
        {"name": "Categories"},
        {"name": "Timestamp"},
    ],
    # 2. CSV Column Mapping: Connects CSV columns to Anki fields (in order)
    "model_builder": [
        {"csv_column": "word"},
        {"csv_column": "pinyin"},
        {"csv_column": "meaning_english"},
        {"csv_column": "meaning_spanish"},
        {"csv_column": "audio"},
        {"csv_column": "sentence_1"},
        {"csv_column": "sentence_2"},
        {"csv_column": "sentence_3"},
        {"csv_column": "translation"},
        {"csv_column": "categories"},
        {"csv_column": "timestamp"},
    ],
    # 3. Media Fields: Tells the generator which columns are files
    "media_fields": [
        {"column_name": "audio", "media_type": "audio"},
    ],
    # 4. "Beautiful Template" (YAML for Templates + CSS)
    "model_templates_yaml": """
main:
  - name: "Card 1 (Word -> All)"
    qfmt: |
      <div class="card-front">
        <h1>{{Word}}</h1>
      </div>
    afmt: |
      {{FrontSide}}
      <hr id=answer>
      <div class="card-back">
        <div class="pinyin">{{Pinyin}}</div>
        <div class="audio">{{Audio}}</div>
        
        <div class="meanings">
          <b>English:</b> {{English Meaning}}<br>
          <b>Spanish:</b> {{Spanish Meaning}}
        </div>
        
        <div class="examples">
          <h3>Examples</h3>
          <ul>
            {{#Example 1}}<li>{{Example 1}}</li>{{/Example 1}}
            {{#Example 2}}<li>{{Example 2}}</li>{{/Example 2}}
            {{#Example 3}}<li>{{Example 3}}</li>{{/Example 3}}
          </ul>
        </div>
        
        <div class="footer">
          <b>Extras:</b> {{Translation (Extras)}}<br>
          <b>Tags:</b> {{Categories}}<br>
          <b>Added:</b> {{Timestamp}}
        </div>
      </div>
css: |
  .card {
    font-family: Arial, 'Noto Sans SC', sans-serif;
    font-size: 20px;
    text-align: center;
    color: black;
    background-color: white;
  }
  .card-front h1 {
    font-family: 'Noto Sans SC', sans-serif;
    font-size: 64px;
    font-weight: 500;
    margin: 0;
  }
  .card-back h1 {
    font-family: 'Noto Sans SC', sans-serif;
    font-size: 48px;
    font-weight: 500;
    margin: 0;
  }
  .pinyin {
    font-size: 24px;
    color: #555;
  }
  .audio {
    margin: 15px 0;
  }
  .meanings {
    margin-top: 20px;
    font-size: 18px;
    text-align: left;
    display: inline-block;
    border-left: 3px solid #0099ff;
    padding-left: 10px;
  }
  .examples {
    margin-top: 20px;
    text-align: left;
    max-width: 90%;
    display: inline-block;
  }
  .examples h3 {
    margin-bottom: 5px;
    font-size: 18px;
    font-weight: bold;
  }
  .examples ul {
    list-style: decimal;
    margin-left: 20px;
  }
  .examples li {
    margin-bottom: 5px;
  }
  .footer {
    margin-top: 30px;
    font-size: 14px;
    color: #888;
    border-top: 1px solid #eee;
    padding-top: 10px;
  }
""",
    # 5. Tag Rules: Auto-generates tags from the 'categories' column
    "tag_rules_yaml": """
- static_tags:
    - "Chinese"
    - "Pipeline"
- prefix: "Category"
  # column: "categories" # Matches the CSV column # This is giving error for it im commenting, fix in the future
  split_by: ","
  # Cleans up the "['...']" format from the CSV
  strip: ' []''"' 
""",
}


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
                {"csv_column": "Word"},  # Maps to Front
                {"csv_column": "Definition"},  # Maps to Back
                {"csv_column": "Sentence"},  # Maps to Example
                {"csv_column": "Sound"},  # Maps to Audio
                {"csv_column": "Picture"},  # Maps to Image (a non-existent col is fine)
                {"csv_column": "Category"},  # Maps to Notes
            ],
            # UPDATED: This now matches your pipeline output CSV by default
            "media_fields": [
                {"column_name": "Sound", "media_type": "audio"},
                {"column_name": "Picture", "media_type": "image"},
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
            st.rerun()  # Rerun to reflect changes in all widgets
        # --- End of New Button ---

        uploaded_csv = st.file_uploader(
            "Upload Vocabulary CSV", type=["csv"], key="anki_csv_uploader"
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
                    df = pd.read_csv(uploaded_csv)
                    df = df.astype(object).where(pd.notnull(df), None)  # Replace NaN

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

                    # 3. Write temp config
                    temp_config_file = Path("temp_anki_config.yaml")
                    with open(temp_config_file, "w", encoding="utf-8") as f:
                        yaml.dump(config_dict, f, allow_unicode=True)

                    # 4. Ensure output dir exists
                    output_path = Path(output_dir)
                    output_path.mkdir(exist_ok=True)

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
