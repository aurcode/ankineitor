import genanki
from loguru import logger
import pandas as pd
import yaml
from pathlib import Path
from typing import List, Set, Union, Optional

from config_schema import AnkiConfig, MediaField

class DeckGenerator:
    """
    Generates Anki decks from a pandas DataFrame based on a validated YAML configuration.
    """
    # Define media format mappings
    MEDIA_FORMATS = {
        'audio': '[sound:{basename}]',
        'image': '<img src="{basename}">',
        'video': '<video controls autoplay muted src="{basename}" />'
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
            with self.config_path.open('r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
            self.config = AnkiConfig.parse_obj(config_data)
            logger.success("Configuration loaded and validated successfully.")
        except FileNotFoundError:
            logger.error(f"Configuration file not found at: {self.config_path}")
            raise
        except Exception as e:
            logger.error(f"Error reading or validating configuration: {e}")
            raise

        self.model = self._create_model()

    def _create_model(self, select_model: str = 'main') -> genanki.Model:
        """Create an Anki model based on the validated configuration."""
        logger.info("Creating Anki model.")
        return genanki.Model(
            self.config.basics.model_id,
            self.config.basics.model_name,
            fields=self.config.model_fields,
            templates=self.config.model_templates[select_model],
            css=self.config.model_templates['css']
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
                logger.warning(f"Media column '{col}' not found in DataFrame. Skipping.")
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
             logger.warning(f"Found {len(missing_files)} missing media file(s). They will be ignored.")

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
            return path_str # Return original value if not a valid, existing path

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
                prefix = f"{rule.prefix}:" if rule.prefix else ""
                
                if rule.split_by:
                    items = [i.strip() for i in content.split(rule.split_by)]
                    tags.extend([f"{prefix}{item}" for item in items])
                else:
                    tags.append(f"{prefix}{content}")
        return tags

    def _build_fields(self, card: pd.Series) -> List[str]:
        """Build fields for an Anki note based on card data."""
        return [str(card.get(field, '')) for field in self.config.model_builder]

    def _create_note(self, card_data: pd.Series) -> Optional[genanki.Note]:
        """Create an Anki note from a row of the DataFrame, skipping if essential fields are empty."""
        fields = self._build_fields(card_data)
        
        # Assume first two fields are essential (e.g., Front, Back)
        if not fields[0] or not fields[1]:
            logger.warning(f"Skipping note creation for row due to empty essential fields: {card_data.name}")
            return None
            
        return genanki.Note(
            model=self.model,
            tags=self._build_tags(card_data),
            fields=fields
        )

    def generate_deck(
        self,
        df: pd.DataFrame,
        deck_name: str,
        output_path: Union[str, Path] = Path("./"),
        strict: bool = False
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
        for _, row in df_formatted.iterrows():
            try:
                note = self._create_note(row)
                if note:
                    deck.add_note(note)
                    note_count += 1
            except Exception as e:
                logger.error(f"Error creating note for row {_.name}: {e}")
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
