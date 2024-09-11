import random
import datetime
from dotenv import load_dotenv
import os
load_dotenv()

def read_file(filepath):
      with open(filepath, 'r', encoding='utf-8') as file:
          return file.read()

CHINESE = {
    'basics': {
        'id': random.randrange(1<<30,1<<31),
        'deck_title': 'tester',
        'model_name': 'testomg',
        'filename': f'{os.getenv('ANKIFILE')}testing.apkg',
        'note_type': 'reading'
    },
    'model_fields': [
        {"name": "Simplified"},
        {"name": "Pinyin"},
        {"name": "Meaning"},
        {"name": "Part"},
        {"name": "Audio"},
        {"name": "developed_by"},
        {"name": "type"},
    ],
    'model_templates': {
         'main': [
              {"name": "Recognition Card",
               "qfmt": read_file('./templates/chinese/front.html'),
               "afmt": read_file('./templates/chinese/back.html'),},
               {"name": "Meaning Card",
                "qfmt": read_file('./templates/chinese/front_audio.html'),
                "afmt": read_file('./templates/chinese/back.html'),}],
         'css': read_file('./templates/chinese/style.css'),
    },
    'model_builder': ['hanzi','pinyin','translation','part','audio']
}

RECOGNITION = {
    'basics': {
        'id': random.randrange(1<<30,1<<31),
        'deck_title': '',
        'model_name': 'recognition_model',
        'filename': f'{os.getenv('ANKIFILE')}recognition-{datetime.datetime.year}-{datetime.datetime.month}-{datetime.datetime.day}.apkg',
        'note_type': 'reading'
    },
    'model_fields': [
        {"name": "Simplified"},
        {"name": "Pinyin"},
        {"name": "Meaning"},
        {"name": "Part"},
        {"name": "Audio"},
        {"name": "developed_by"},
        {"name": "type"},
    ],
    'model_templates': {
         'main': [
              {"name": "Recognition Card",
               "qfmt": read_file('./templates/chinese/front.html'),
               "afmt": read_file('./templates/chinese/back.html'),},
            ],
         'css': read_file('./templates/chinese/style.css'),
    },
    'model_builder': ['hanzi','pinyin','translation','part','audio']
}

PHOTO_PHOTO_BASIC = {
    'basics': {
        'id': random.randrange(1<<30,1<<31),
        'deck_title': 'testing for image',
        'model_name': 'image_image',
        'filename': f'{os.getenv('ANKIFILE')}testing_image.apkg',
        'note_type': 'study'
    },
    'model_fields': [
        {"name": "ImageFront"},
        {"name": "ImageBack"},
        {"name": "developed_by"},
        {"name": "image-image"},
    ],
    'model_templates': {
         'main': [
              {'name': "Recognition Card",
               'qfmt': '<img src="{{ImageFront}}">',
               'afmt': '{{FrontSide}}<hr id="answer"><img src="{{ImageBack}}">',}],
         'css': read_file('./templates/chinese/style.css'),
    },
    'model_builder': ['image_front', 'image_back']
}