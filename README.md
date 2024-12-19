Run with Docker Compose
```
docker-compose up --build
```

localhost:8000/docs

Next format
```
{
  "dataframe": [
    {
      "Title": "What is photosynthesis?",
      "Desc": "Is the process by which plants, algae, and some bacteria convert light energy into chemical energy stored in glucose. It involves the absorption of light by chlorophyll, the utilization of carbon dioxide, and the production of oxygen as a byproduct."
    },
    {
      "Title": "What is Mitosis",
      "Desc": "Is a type of cell division in which a single cell divides to produce two identical daughter cells. This process is crucial for growth, development, and repair in multicellular organisms."
    }
  ],
  "config": {
    "basics": {
      "id": 123456789,
      "deck_title": "First Deck",
      "model_name": "Basic Model",
      "filename": "first_deck.apkg",
      "note_type": "reading"
    },
    "model_fields": [
      {"name": "Title"},
      {"name": "Desc"}
    ],
    "model_templates": {
      "main": [
        {
          "name": "Basic Card",
          "qfmt": "{{Title}}",
          "afmt": "{{FrontSide}}<br/>{{Desc}}"
        },
        {
          "name": "Reverse Card",
          "qfmt": "{{Desc}}",
          "afmt": "{{FrontSide}}<br/>{{Desc}}"
        }
      ],
      "css": ".card { font-family: Arial; font-size: 20px; }"
    },
    "model_builder": ["Title", "Desc"]
  }
}
```

For audios and images
```
{
  "dataframe": [
    {
      "image_front": "/opt/input/image1.jpg",
      "image_back": "/opt/input/image2.jpg",
      "audio": "/opt/input/audio.mp3"
    }
  ],
  "config": {
    "basics": {
        "id": "123456",
        "deck_title": "Image to Image",
        "model_name": "image_image",
        "filename": "images.apkg",
        "note_type": "study"
    },
    "model_fields": [
        {"name": "ImageFront"},
        {"name": "ImageBack"},
        {"name": "Audio"}
    ],
    "model_templates": {
        "main": [
            {"name": "Recognition Card",
             "qfmt": "<img src=\"{{ImageFront}}\">",
             "afmt": "{{Audio}}<br/>{{FrontSide}}<hr id=\"answer\">{{ImageBack}}"}
        ],
        "css": " "
    },
    "model_builder": ["image_front", "image_back","audio"]
  }
}
```