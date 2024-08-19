import genanki
from tqdm import tqdm
#from .preconfigurations import CHINESE as CONFIG
from .preconfigurations import PHOTO_PHOTO_BASIC as CONFIG

#class CardsGenerator:

class DeckGenerator:
    def __init__(self, df):
        self.columns = list(df.columns)
        self.anki_cards = df.to_dict(orient='index')
        self.media_list = list()
        self.model = self.create_model()
        self.my_deck = genanki.Deck(CONFIG['basics']['id'], CONFIG['basics']['deck_title'])

    def create_model(self, select_model: str = 'main'):
        return genanki.Model(
            CONFIG['basics']['id'],
            CONFIG['basics']['model_name'],
            fields=CONFIG['model_fields'],
            templates=CONFIG['model_templates'][select_model],
            css=CONFIG['model_templates']['css']
        )

    def __build_media(self):
        media_columns = [col for col in self.columns if 'audio' in col.lower() or 'image' in col.lower()]
        for key, entry in tqdm(self.anki_cards.items()):
            for media_col in media_columns:
                if media_col in entry:
                    filename = entry[media_col]
                    self.media_list.append(filename)
                    if '.mp3' in filename:
                        self.anki_cards[key][media_col] = '[sound:' + filename.split('/')[-1] + ']'
                    if '.png' in filename or '.jpg' in filename:
                        self.anki_cards[key][media_col] = filename.split('/')[-1]

    def create_notes(self, model: genanki.Model):
        self.__build_media()
        for card in tqdm(self.anki_cards):
            self.my_deck.add_note(self._create_note(model, self.anki_cards[card]))

    def __build_tags(self, card):
        tags = list()
        if 'time' in self.columns:
            tags.append('time:' + card['time'])
        if 'lesson' in self.columns:
            tags.append('lesson:' + str(card['lesson']))

        return tags

    def __build_fields(self, card):
        return [card[i] for i in CONFIG['model_builder'] ]

    def _create_note(self, model: genanki.Model, card):
        tags = self.__build_tags(card)
        fields = self.__build_fields(card)

        for i in ['@AURCODE', CONFIG['basics']['note_type']]:
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
        my_package.write_to_file(CONFIG['basics']['filename'])

    def generate_decks(self):
        self.create_notes(self.model)
        self.write_decks_to_file()
        print(self.media_list)