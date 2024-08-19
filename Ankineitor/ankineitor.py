import tqdm
import random
import genanki

class DeckGenerator:
    def __init__(self, df, anki_deck_title, anki_model_name, model_style_file, model_front_file, model_back_file, deck_filename):
        self.df = df
        self.anki_deck_title = anki_deck_title
        self.anki_model_name = anki_model_name
        self.model_style = self.read_file(model_style_file)
        self.model_front = self.read_file(model_front_file)
        self.model_back = self.read_file(model_back_file)
        self.deck_filename = deck_filename
        self.model_id = random.randrange(1 << 30, 1 << 31)
        self.file = lambda text: str(text) + '-zh.mp3'
        self.media_list = []
        self.model = self.create_model(self.model_id, "character")
        self.my_deck = genanki.Deck(self.model_id, self.anki_deck_title)

    def read_file(self, filepath):
        with open(filepath, 'r', encoding='utf-8') as file:
            return file.read()

    def create_model(self, model_id, template_name):
        return genanki.Model(
            model_id,
            self.anki_model_name,
            fields=[
                {"name": "Simplified"},
                {"name": "Pinyin"},
                {"name": "Meaning"},
                {"name": "Part"},
                {"name": "Audio"},
                {"name": "developed_by"},
                {"name": "type"},
            ],
            templates=[
                {
                    "name": template_name,
                    "qfmt": self.model_front,
                    "afmt": self.model_back,
                }
            ],
            css=self.model_style
        )

    def add_notes_to_decks(self):
        for index, row in tqdm(self.df.iterrows(), total=self.df.shape[0]):
            media_name = self.file(row['audio'])
            if media_name != '.mp3':
                self.media_list.append(media_name)
                sound_name = '[sound:' + media_name.split('/')[-1] + ']'
                note_character = self.create_note(row, sound_name, "reading")
                self.my_deck.add_note(note_character)

    def create_note(self, row, sound_name, note_type):
        tags = [
            note_type,
            #'lession:' + str(row['lession']),
            'time:' + str(row['time']),
            "@AURCODE"
        ]
        return genanki.Note(
            model=self.model,
            tags=tags,
            fields=[
                str(row['hanzi']),
                str(row['pinyin']),
                str(row['translation']),
                str(row['part']),
                sound_name,
                '@AURCODE',
                note_type
            ]
        )

    def write_decks_to_file(self):
        my_package = genanki.Package(self.my_deck)
        my_package.media_files = self.media_list
        my_package.write_to_file(self.deck_filename)

    def generate_decks(self):
        self.add_notes_to_decks()
        self.write_decks_to_file()
        print(self.media_list)
