import genanki
from tqdm import tqdm
import pandas as pd

#class CardsGenerator:

class DeckGenerator:
    def __init__(self, df, config):
        self.columns = list(df.columns)
        self.anki_cards = df.to_dict(orient='index')
        self.media_list = list()
        self.CONFIG = config
        self.model = self.create_model()
        self.my_deck = genanki.Deck(self.CONFIG['basics']['id'], self.CONFIG['basics']['deck_title'])

    def create_model(self, select_model: str = 'main'):
        return genanki.Model(
            self.CONFIG['basics']['id'],
            self.CONFIG['basics']['model_name'],
            fields=self.CONFIG['model_fields'],
            templates=self.CONFIG['model_templates'][select_model],
            css=self.CONFIG['model_templates']['css']
        )

    def __build_media(self):
        media_columns = [col for col in self.columns if 'audio' in col.lower() or 'image' in col.lower()]
        for key, entry in tqdm(self.anki_cards.items()):
            for media_col in media_columns:
                # Ensure the media_col value is a string before proceeding
                if media_col in entry and isinstance(entry[media_col], str):
                    filename = entry[media_col]
                    self.media_list.append(filename)
                    print(filename)
                    if '.mp3' in filename:
                        self.anki_cards[key][media_col] = '[sound:' + filename.split('\\')[-1] + ']'
                    if '.png' in filename or '.jpg' in filename:
                        self.anki_cards[key][media_col] = filename.split('\\')[-1]
                else:
                    # Handle cases where entry[media_col] is not a string (like NaN or float)
                    print(f"Skipping media column {media_col} for key {key} because it is not a valid string.")

    def create_notes(self, model: genanki.Model):
        self.__build_media()
        for card in tqdm(self.anki_cards):
            self.my_deck.add_note(self._create_note(model, self.anki_cards[card]))

    def __build_tags(self, card):
        tags = list()
        if 'categories' in self.columns and isinstance(card.get('categories'), str):
            [tags.append("课程:"+i) for i in card['categories'].split(', ')]
        if 'time' in self.columns and isinstance(card.get('time'), str):
            tags.append('time:' + card['time'])
        if 'lesson' in self.columns and card.get('lesson') is not None:
            tags.append('lesson:' + str(card['lesson']))

        return tags

    def __build_fields(self, card):
        return [card[i] for i in self.CONFIG['model_builder'] ]

    def _create_note(self, model: genanki.Model, card):
        tags = self.__build_tags(card)
        fields = self.__build_fields(card)

        print(tags)
        print(fields)

        for i in ['@AURCODE', self.CONFIG['basics']['note_type']]:
            tags.append(i)
            fields.append(i)

        return genanki.Note(
            model=model,
            tags=tags,
            fields=fields
        )

    def write_decks_to_file(self):
        my_package = genanki.Package(self.my_deck)
        my_package.media_files = self.media_list
        my_package.write_to_file(self.CONFIG['basics']['filename'])
        my_package.write_to_collection_from_addon

    def generate_decks(self):
        self.create_notes(self.model)
        self.write_decks_to_file()
        print(self.media_list)
        return self.CONFIG['basics']['filename']
