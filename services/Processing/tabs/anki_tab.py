import streamlit as st
import pandas as pd
import yaml
from pathlib import Path
from loguru import logger

# Import DeckGenerator
from deck_generator import DeckGenerator

# --- Default Anki Configs (from your example) ---
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
    - "RefactoredDeck"
- prefix: "Course"
  column: "Category"
  split_by: ","
- prefix: "Lesson"
  column: "Lesson"
"""


def render_anki_tab():
    """
    Renders the 'Anki Deck Generator' tab.
    """
    st.header("Anki Deck Generator")

    # --- Initialize Session State for Config ---
    if "anki_config" not in st.session_state:
        st.session_state.anki_config = {
            "model_id": 1607392319,
            "model_name": "AURCODE Refactored Model",
            "deck_id": 1234567890,
            "note_type": "Vocabulary",
            "model_fields": [
                {"name": "Front"},
                {"name": "Back"},
                {"name": "Example"},
                {"name": "Audio"},
                {"name": "Image"},
                {"name": "Notes"},
            ],
            "model_builder": [
                {"csv_column": "Word"},
                {"csv_column": "Definition"},
                {"csv_column": "Sentence"},
                {"csv_column": "Sound"},
                {"csv_column": "Picture"},
                {"csv_column": "ExtraInfo"},
            ],
            "media_fields": [
                {"column_name": "Sound", "media_type": "audio"},
                {"column_name": "Picture", "media_type": "image"},
            ],
            "model_templates_yaml": DEFAULT_MODEL_TEMPLATES_YAML,
            "tag_rules_yaml": DEFAULT_TAG_RULES_YAML,
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
            if not uploaded_csv:
                st.warning("Please upload a vocabulary CSV file.")
            else:
                try:
                    with st.spinner("Generating Anki Deck..."):
                        # 1. Load Data
                        logger.info(
                            f"Reading data from uploaded file: {uploaded_csv.name}"
                        )
                        df = pd.read_csv(uploaded_csv)
                        df = df.astype(object).where(
                            pd.notnull(df), None
                        )  # Replace NaN

                        # 2. Assemble Config
                        logger.info("Assembling configuration from UI...")
                        config_dict = {
                            "basics": {
                                "model_id": cfg["model_id"],
                                "model_name": cfg["model_name"],
                                "deck_id": cfg["deck_id"],
                                "note_type": cfg["note_type"],
                            },
                            "model_fields": cfg["model_fields"].to_dict("records"),
                            "model_builder": cfg["model_builder"][
                                "csv_column"
                            ].tolist(),
                            "media_fields": cfg["media_fields"].to_dict("records"),
                            "model_templates": yaml.safe_load(
                                cfg["model_templates_yaml"]
                            ),
                            "tag_rules": yaml.safe_load(cfg["tag_rules_yaml"]),
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
                            st.success(
                                f"Deck '{deck_name}.apkg' generated successfully!"
                            )
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
                    logger.critical(f"An error occurred during deck generation: {e}")
                    st.error(f"An unexpected error occurred: {e}")
                    # Clean up temp file on error too
                    if "temp_config_file" in locals() and temp_config_file.exists():
                        temp_config_file.unlink()
