import re
import genanki
from loguru import logger
import pandas as pd
import yaml
from pathlib import Path
from typing import List, Set, Union, Optional

from configs.config_schema import AnkiConfig, MediaField


class DeckGenerator:
    """
    Generates Anki decks from a pandas DataFrame based on a validated YAML configuration.
    """

    # Define media format mappings
    MEDIA_FORMATS = {
        "audio": "[sound:{basename}]",
        "image": '<img src="{basename}">',
        "video": '<video controls autoplay muted src="{basename}" />',
    }

    def __init__(self, config_path: Union[str, Path]):
        """
        Initializes the DeckGenerator with a configuration from a YAML file.

        Args:
            config_path (Union[str, Path]): The path to the YAML configuration file.
        """
        self.config_path = Path(config_path)
        logger.info(f"Loading configuration from {self.config_path}")
        try:
            with self.config_path.open("r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f)
            self.raw_config_data = config_data
            self.config = AnkiConfig.parse_obj(config_data)
            logger.success("Configuration loaded and validated successfully.")
        except FileNotFoundError:
            logger.error(f"Configuration file not found at: {self.config_path}")
            raise
        except Exception as e:
            logger.error(f"Error reading or validating configuration: {e}")
            raise

        self.model = self._create_model()

    def _create_model(self, select_model: str = "main") -> genanki.Model:
        """Create an Anki model based on the validated configuration."""
        logger.info("Creating Anki model.")

        # --- START REPLACEMENT CODE ---

        # Use Pydantic for simple, validated values
        model_id = self.config.basics.model_id
        model_name = self.config.basics.model_name

        # Use the validated Pydantic model for fields, and raw data for templates/css
        # as genanki expects simple dicts/lists.
        try:
            # Convert Pydantic model list back to a list of dicts for genanki
            validated_fields = [field.dict() for field in self.config.model_fields]

            raw_templates = self.raw_config_data["model_templates"][select_model]
            raw_css = self.raw_config_data["model_templates"]["css"]
        except KeyError as e:
            logger.critical(
                f"Config file {self.config_path} is missing required key: {e}"
            )
            raise
        except TypeError as e:
            logger.critical(
                f"Config file structure is corrupt. 'model_templates' is likely not a dict. Error: {e}"
            )
            raise

        logger.info(f"Passing {len(validated_fields)} fields to genanki.Model")

        return genanki.Model(
            model_id,
            model_name,
            fields=validated_fields,
            templates=raw_templates,
            css=raw_css,
        )

    def _collect_media_files(self, df: pd.DataFrame, strict: bool = False) -> Set[Path]:
        """
        Collect all valid media file paths from the DataFrame.

        Args:
            df (pd.DataFrame): The input DataFrame.
            strict (bool): If True, raises an error for any missing media files.

        Returns:
            Set[Path]: A set of unique, existing media file paths.
        """
        logger.info("Collecting media files.")
        media_files: Set[Path] = set()
        missing_files: List[str] = []

        for media_field in self.config.media_fields:
            col = media_field.column_name
            if col not in df.columns:
                logger.warning(
                    f"Media column '{col}' not found in DataFrame. Skipping."
                )
                continue

            for filename in df[col].dropna():
                if isinstance(filename, str) and filename.strip():
                    path = Path(filename)
                    if path.exists():
                        media_files.add(path)
                    else:
                        missing_files.append(filename)

        if strict and missing_files:
            error_msg = f"Strict mode enabled. Missing {len(missing_files)} media file(s): {missing_files}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)

        if missing_files:
            logger.warning(
                f"Found {len(missing_files)} missing media file(s). They will be ignored."
            )

        logger.info(f"Collected {len(media_files)} unique media files.")
        return media_files

    def _format_media_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Return a new DataFrame with media file paths replaced by Anki HTML tags.

        Args:
            df (pd.DataFrame): The input DataFrame.

        Returns:
            pd.DataFrame: A new DataFrame with formatted media columns.
        """
        logger.info("Formatting media fields in DataFrame.")
        df_formatted = df.copy()

        def format_path(path_str: str, media_type: str) -> str:
            if isinstance(path_str, str) and path_str.strip():
                path = Path(path_str)
                if path.exists():
                    template = self.MEDIA_FORMATS.get(media_type, "")
                    return template.format(basename=path.name)
            return path_str  # Return original value if not a valid, existing path

        for media_field in self.config.media_fields:
            col = media_field.column_name
            media_type = media_field.media_type
            if col in df_formatted.columns:
                df_formatted[col] = df_formatted[col].apply(
                    lambda x: format_path(x, media_type)
                )
        return df_formatted

    def _build_tags(self, card: pd.Series) -> List[str]:
        """Build tags for an Anki note based on config-driven rules."""
        tags = []
        for rule in self.config.tag_rules:
            if rule.static_tags:
                tags.extend(rule.static_tags)

            if rule.column and rule.column in card and pd.notna(card[rule.column]):
                content = str(card[rule.column])
                prefix = f"{rule.prefix}::" if rule.prefix else ""

                # Use regex to find all quoted strings, which is robust for formats
                # like "['item 1', 'item 2']" or '["item1", "item2"]'
                items = re.findall(r'["\'](.*?_*)["\']', content)

                if items:
                    # No need to split or strip further, regex handles it
                    tags.extend([f"{prefix}{item}" for item in items])
                elif content:
                    # Fallback for simple, non-list strings
                    # Clean the content before adding
                    if rule.strip_chars:
                        content = content.strip(rule.strip_chars)
                    if content:
                        tags.append(f"{prefix}{content}")

        # Return a list of unique, non-empty tags
        return sorted(list(set(filter(None, tags))))

    def _build_fields(self, card: pd.Series) -> List[str]:
        """Build fields for an Anki note based on card data."""
        return [str(card.get(field) or "") for field in self.config.model_builder]

    def _create_note(self, card_data: pd.Series) -> Optional[genanki.Note]:
        """Create an Anki note from a row of the DataFrame, skipping if essential fields are empty."""
        fields = self._build_fields(card_data)

        # Assume first two fields are essential (e.g., Front, Back)
        if not fields[0] or not fields[1]:
            logger.warning(
                f"Skipping note creation for row due to empty essential fields: {card_data.name}"
            )
            return None

        return genanki.Note(
            model=self.model, tags=self._build_tags(card_data), fields=fields
        )

    def generate_deck(
        self,
        df: pd.DataFrame,
        deck_name: str,
        output_path: Union[str, Path] = Path("./"),
        strict: bool = False,
    ) -> Path:
        """
        Generates an Anki deck from a pandas DataFrame.

        Args:
            df (pd.DataFrame): The DataFrame containing card data.
            deck_name (str): The name of the deck to be generated.
            output_path (Union[str, Path]): The directory to save the .apkg file.
            strict (bool): If True, stops execution if any media file is not found.

        Returns:
            Path: The filepath of the generated .apkg file.
        """
        logger.info(f"Starting deck generation for '{deck_name}'.")

        deck = genanki.Deck(self.config.basics.deck_id, deck_name)
        media_files = self._collect_media_files(df, strict=strict)
        df_formatted = self._format_media_df(df)

        logger.info("Creating notes...")
        note_count = 0
        for row_index, row in df_formatted.iterrows():
            try:
                note = self._create_note(row)
                if note:
                    deck.add_note(note)
                    note_count += 1
            except Exception as e:
                logger.error(f"Error creating note for row {row_index}: {e}")
        logger.info(f"Created {note_count} notes from {len(df)} rows.")

        logger.info("Writing deck to file...")
        try:
            package = genanki.Package(deck)
            package.media_files = [str(p) for p in media_files]
            logger.info(f"Adding {len(media_files)} media files to the package.")

            output_dir = Path(output_path)
            output_dir.mkdir(parents=True, exist_ok=True)
            filepath = output_dir / f"{deck_name}.apkg"

            package.write_to_file(filepath)
            logger.success(f"Deck successfully written to {filepath}.")
            return filepath
        except Exception as e:
            logger.error(f"Error writing deck to file: {e}")
            raise


def main():
    """
    Main function to run the deck generation process.
    """
    # Define paths based on the project structure
    CONFIG_PATH = Path("config.yaml")
    DATA_PATH = Path("data/vocabulary.csv")
    OUTPUT_DIR = Path("output/")
    DECK_NAME = "My English Vocabulary"

    # --- Pre-run Checks ---
    if not CONFIG_PATH.exists():
        logger.error(f"Configuration file not found at '{CONFIG_PATH}'. Exiting.")
        return

    if not DATA_PATH.exists():
        logger.error(f"Data file not found at '{DATA_PATH}'. Exiting.")
        return

    # --- Deck Generation ---
    try:
        # 1. Load the data from CSV into a pandas DataFrame
        logger.info(f"Reading data from {DATA_PATH}...")
        df = pd.read_csv(DATA_PATH)
        df = df.astype(object).where(pd.notnull(df), None)  # Replace NaN with None

        # 2. Initialize the DeckGenerator with the config file
        generator = DeckGenerator(config_path=CONFIG_PATH)

        # 3. Generate the deck
        generator.generate_deck(
            df=df,
            deck_name=DECK_NAME,
            output_path=OUTPUT_DIR,
            strict=False,  # Set to True to fail if media is missing
        )

    except Exception as e:
        logger.error(f"An unexpected error occurred during deck generation: {e}")


if __name__ == "__main__":
    main()
