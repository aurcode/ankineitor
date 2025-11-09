import genanki
from loguru import logger
import pandas as pd
import os
from dotenv import load_dotenv
import yaml
from pathlib import Path

load_dotenv()

class DeckGenerator:
    """
    Generates Anki decks from a pandas DataFrame based on a YAML configuration.
    """
    # Define common media extensions for automatic handling
    AUDIO_EXTENSIONS = {'.mp3', '.wav', '.ogg', '.flac', '.m4a'}
    IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'}
    VIDEO_EXTENSIONS = {'.mp4', '.webm', '.ogv', '.mov', '.avi', '.mkv'}

    def __init__(self, config_path: str):
        """
        Initializes the DeckGenerator with a configuration from a YAML file.

        Args:
            config_path (str): The path to the YAML configuration file.
        """
        logger.info(f"Loading configuration from {config_path}")
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)
        except FileNotFoundError:
            logger.error(f"Configuration file not found at: {config_path}")
            raise
        except Exception as e:
            logger.error(f"Error reading or parsing YAML configuration: {e}")
            raise

        self.model = self._create_model()

    def _create_model(self, select_model: str = 'main') -> genanki.Model:
        """Create an Anki model based on the provided configuration."""
        logger.info("Creating Anki model.")
        return genanki.Model(
            self.config['basics']['model_id'],
            self.config['basics']['model_name'],
            fields=self.config['model_fields'],
            templates=self.config['model_templates'][select_model],
            css=self.config['model_templates']['css']
        )

    def _build_media(self, df: pd.DataFrame) -> list[str]:
        """
        Process media files, update DataFrame, and return a list of media paths.
        Supports various audio, image, and video formats.
        """
        logger.info("Building media list and updating DataFrame.")
        media_list = []
        media_columns = [col for col in df.columns if any(keyword in col.lower() for keyword in ['audio', 'image', 'video'])]

        for index, row in df.iterrows():
            for media_col in media_columns:
                filename = row.get(media_col)
                if isinstance(filename, str) and os.path.exists(filename):
                    file_ext = os.path.splitext(filename)[1].lower()
                    basename = os.path.basename(filename)

                    media_list.append(filename)

                    # Update DataFrame with Anki-compatible HTML/sound tags
                    if file_ext in self.AUDIO_EXTENSIONS:
                        df.at[index, media_col] = f'[sound:{basename}]'
                    elif file_ext in self.IMAGE_EXTENSIONS:
                        df.at[index, media_col] = f'<img src="{basename}">'
                    elif file_ext in self.VIDEO_EXTENSIONS:
                        df.at[index, media_col] = f'<video controls autoplay muted src="{basename}" />'
                    else:
                        logger.warning(f"Unsupported media type for file: {filename}")
                elif filename:
                    logger.debug(f"Skipping media for row {index}. File not found or invalid path: {filename}")

        return list(set(media_list))

    def _build_tags(self, card: pd.Series) -> list:
        """Build tags for an Anki note based on card data."""
        tags = []
        if 'categories' in card and isinstance(card.get('categories'), str):
            tags.extend([f"课程:{i.strip()}" for i in card['categories'].split(',')])

        if 'time' in card and isinstance(card.get('time'), str):
            tags.append(f"time:{card['time']}")

        if 'lesson' in card and card.get('lesson') is not None:
            tags.append(f"lesson:{card['lesson']}")

        tags.extend(['@AURCODE', self.config['basics']['note_type']])
        return tags

    def _build_fields(self, card: pd.Series) -> list:
        """Build fields for an Anki note based on card data."""
        return [str(card.get(field, '')) for field in self.config['model_builder']]

    def _create_note(self, card_data: pd.Series) -> genanki.Note:
        """Create an Anki note from a row of the DataFrame."""
        return genanki.Note(
            model=self.model,
            tags=self._build_tags(card_data),
            fields=self._build_fields(card_data)
        )

    def generate_deck_from_dataframe(self, df: pd.DataFrame, deck_name: str) -> str:
        """
        Generates an Anki deck from a pandas DataFrame.

        Args:
            df (pd.DataFrame): The DataFrame containing card data.
            deck_name (str): The name of the deck to be generated.

        Returns:
            str: The filepath of the generated .apkg file.
        """
        logger.info(f"Starting deck generation for '{deck_name}'.")

        deck = genanki.Deck(self.config['basics']['deck_id'], deck_name)
        media_files = self._build_media(df)

        logger.info("Creating notes...")
        for _, row in df.iterrows():
            try:
                note = self._create_note(row)
                deck.add_note(note)
            except Exception as e:
                logger.error(f"Error creating note for row {_.name}: {e}")
        logger.info(f"Created {len(df)} notes.")

        logger.info("Writing deck to file...")
        try:
            package = genanki.Package(deck)
            package.media_files = media_files
            logger.info(f"Adding {len(media_files)} media files to the package.")

            output_dir = '/opt/output/' if os.getenv('DOCKER') else './'
            os.makedirs(output_dir, exist_ok=True)
            filepath = os.path.join(output_dir, f"{deck_name}.apkg")
            
            package.write_to_file(filepath)
            logger.info(f"Deck successfully written to {filepath}.")
            return filepath
        except Exception as e:
            logger.error(f"Error writing deck to file: {e}")
            raise