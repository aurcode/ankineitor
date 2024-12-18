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
      "Title": "Hiiii",
      "Descp": "Hellou!",
      "type": "test"
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
      {"name": "Desc"},
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
          "afmt": "{{Title}}"
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