import genanki
from loguru import logger
import pandas as pd
import os
from dotenv import load_dotenv

load_dotenv()

class DeckGenerator:
    def __init__(self, df: pd.DataFrame, config: dict):
        self.columns = list(df.columns)
        self.anki_cards = df.to_dict(orient='index')
        self.media_list = []
        self.config = config
        self.model = self._create_model()
        self.deck = genanki.Deck(self.config['basics']['id'], self.config['basics']['deck_title'])

    def _create_model(self, select_model: str = 'main') -> genanki.Model:
        """Create an Anki model based on the provided configuration."""
        logger.info("Creating Anki model.")
        return genanki.Model(
            self.config['basics']['id'],
            self.config['basics']['model_name'],
            fields=self.config['model_fields'],
            templates=self.config['model_templates'][select_model],
            css=self.config['model_templates']['css']
        )

    def _build_media(self):
        """Process media files and update the media list."""
        logger.info("Building media list from the provided DataFrame.")
        media_columns = [col for col in self.columns if 'audio' in col.lower() or 'image' in col.lower()]
        total_cards = len(self.anki_cards)
        processed_count = 0

        for key, entry in self.anki_cards.items():
            for media_col in media_columns:
                try:
                    if media_col in entry and isinstance(entry[media_col], str):
                        filename = entry[media_col]
                        self.media_list.append(filename)
                        logger.info(filename)
                        # Update media references for Anki compatibility
                        if '.mp3' in filename:
                            self.anki_cards[key][media_col] = f'[sound:{filename.split("/")[-1]}]'
                        elif '.png' in filename or '.jpg' in filename:
                            self.anki_cards[key][media_col] = filename.split("/")[-1]
                    else:
                        logger.debug(f"Skipping invalid media for key {key}, column {media_col}.")
                except Exception as e:
                    logger.error(f"Error processing media for key {key}, column {media_col}: {e}")
            processed_count += 1
            if processed_count % 100 == 0 or processed_count == total_cards:
                logger.info(f"Processed {processed_count}/{total_cards} cards for media.")

    def _build_tags(self, card: dict) -> list:
        """Build tags for an Anki note based on card data."""
        tags = []

        if 'categories' in self.columns and isinstance(card.get('categories'), str):
            tags.extend([f"课程:{i}" for i in card['categories'].split(', ')])

        if 'time' in self.columns and isinstance(card.get('time'), str):
            tags.append(f"time:{card['time']}")

        if 'lesson' in self.columns and card.get('lesson') is not None:
            tags.append(f"lesson:{card['lesson']}")

        return tags

    def _build_fields(self, card: dict) -> list:
        """Build fields for an Anki note based on card data."""
        return [card.get(field, '') for field in self.config['model_builder']]

    def _create_note(self, model: genanki.Model, card: dict) -> genanki.Note:
        """Create an Anki note based on card data."""
        tags = self._build_tags(card)
        fields = self._build_fields(card)

        # Append additional metadata tags and fields
        tags.extend(['@AURCODE', self.config['basics']['note_type']])
        #fields.extend(['@AURCODE', self.config['basics']['note_type']])

        return genanki.Note(
            model=model,
            tags=tags,
            fields=fields
        )

    def create_notes(self):
        """Create and add notes to the deck."""
        logger.info("Creating notes for the deck.")
        self._build_media()

        total_cards = len(self.anki_cards)
        processed_count = 0

        for card_id, card_data in self.anki_cards.items():
            try:
                note = self._create_note(self.model, card_data)
                self.deck.add_note(note)
            except Exception as e:
                logger.error(f"Error creating note for card ID {card_id}: {e}")

            processed_count += 1
            if processed_count % 100 == 0 or processed_count == total_cards:
                logger.info(f"Created {processed_count}/{total_cards} notes.")

    def write_deck_to_file(self):
        """Write the deck and media files to an Anki package."""
        logger.info("Writing deck to file.")
        try:
            package = genanki.Package(self.deck)
            package.media_files = self.media_list
            logger.info(self.media_list)
            filepath = '/opt/output/' + self.config['basics']['filename'] if os.getenv('DOCKER') else self.config['basics']['filename']
            package.write_to_file(filepath)
            logger.info(f"Deck written to {filepath}.")
        except Exception as e:
            logger.error(f"Error writing deck to file: {e}")

    def generate_deck(self) -> str:
        """Generate the Anki deck and return the file name."""
        logger.info("Generating Anki deck.")
        self.create_notes()
        self.write_deck_to_file()
        logger.info("Anki deck generation completed.")
        return self

    def get_filepath(self) -> str:
        """Return the file path of the generated deck."""
        return self.config['basics']['filename']