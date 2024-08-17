import random
import genanki

class DeckGenerator:
    def __init__(self, df, anki_deck_title, anki_model_name, model_style_file, model_front_character_file, model_front_audio_file, model_back_file, deck_filename):
        self.df = df
        self.anki_deck_title = anki_deck_title
        self.anki_model_name = anki_model_name
        self.model_style = self.read_file(model_style_file)
        self.model_front_character = self.read_file(model_front_character_file)
        self.model_front_audio = self.read_file(model_front_audio_file)
        self.model_back = self.read_file(model_back_file)
        self.deck_filename = deck_filename
        self.model_id = random.randrange(1 << 30, 1 << 31)
        self.model_id2 = random.randrange(1 << 30, 1 << 31)
        self.file = lambda text: str(text) + '-zh.mp3'
        self.media_list = []

        self.model_character = self.create_model(self.model_id, "character")
        self.model_audio = self.create_model(self.model_id2, "audio")

        self.my_deck = genanki.Deck(self.model_id, self.anki_deck_title)
        self.my_deck2 = genanki.Deck(self.model_id2, self.anki_deck_title)

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
                    "qfmt": self.get_front_template(template_name),
                    "afmt": self.model_back,
                }
            ],
            css=self.model_style
        )

    def get_front_template(self, template_name):
        return self.model_front_character if template_name == "character" else self.model_front_audio

    def add_notes_to_decks(self):
        for index, row in self.df.iterrows():
            media_name = self.file(row['path'])
            if media_name != '.mp3':
                self.media_list.append(media_name)
                sound_name = '[sound:' + media_name + ']'

                note_character = self.create_note(row, sound_name, "character")
                note_audio = self.create_note(row, sound_name, "audio")

                self.my_deck.add_note(note_character)
                self.my_deck2.add_note(note_audio)

    def create_note(self, row, sound_name, note_type):
        tags = [
            note_type,
            'lession:' + str(row['lession']),
            'date:' + str(row['created']),
            "@AURCODE"
        ]
        return genanki.Note(
            model=self.model_character if note_type == "character" else self.model_audio,
            tags=tags,
            fields=[
                str(row['hanzi']),
                str(row['pinyin']),
                str(row['mean']),
                str(row['part']),
                sound_name,
                '@AURCODE',
                note_type
            ]
        )

    def write_decks_to_file(self):
        my_package = genanki.Package(self.my_deck)
        my_package.media_files = self.media_list
        my_package.write_to_file('r-' + self.deck_filename)

        my_package2 = genanki.Package(self.my_deck2)
        my_package2.media_files = self.media_list
        my_package2.write_to_file('w-' + self.deck_filename)

    def generate_decks(self):
        self.add_notes_to_decks()
        self.write_decks_to_file()
        print(self.media_list)
