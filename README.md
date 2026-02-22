# Ankineitor 🤖

Ankineitor is a powerful, configurable tool designed to automate the creation of Anki flashcard decks, primarily for language learning. It transforms a simple list of words into a rich, multimedia Anki deck, complete with translations, Pinyin, audio, and AI-generated example sentences.

The application is built with a Streamlit web interface, providing a user-friendly control panel to manage the entire data processing and deck generation pipeline.

## ✨ Features

- **Automated Anki Deck Creation**: Generates `.apkg` files that can be directly imported into Anki.
- **Configurable Pipeline**: Customize the data transformations to fit your learning needs.
- **Multimedia Enrichment**: Automatically adds audio pronunciations, translations, and Pinyin to your flashcards.
- **Two-Stage AI Image Generation**: Stage 1 (text LLM) builds a strict master image prompt with Victorian gaslamp constraints, Stage 2 (image model) renders it and saves the file path to `picture`.
- **LLM Integration**: Leverages Large Language Models (LLMs) to generate meaningful example sentences and detailed explanations for vocabulary.
- **Efficient Caching**: Uses a database to cache processed words, so you only process new vocabulary, saving time and resources.
- **User-Friendly Web Interface**: A Streamlit-based control panel makes it easy to run the pipeline and generate decks.
- **Dockerized**: Includes `docker-compose.yml` for easy setup and deployment.

## ⚙️ How It Works

The project is structured as a data processing pipeline with a web interface.

1.  **Input**: You provide a list of words through the Streamlit UI.
2.  **Processing Pipeline**: The application processes each word through a series of transformations:
    - **Pinyin Transformation**: Generates the Pinyin for Chinese characters.
    - **Translation Transformation**: Translates words into a target language (e.g., Spanish).
    - **Audio Transformation**: Creates audio files for pronunciation.
    - **LLM Transformation**: Uses an LLM to generate example sentences and other contextual information.
    - **LLM Image Prompt Transformation (Stage 1)**: Classifies each term and generates a strict master image prompt.
    - **LLM Image Transformation (Stage 2)**: Renders the Stage 1 master prompt into a final flashcard-friendly image.
3.  **Deck Generation**: The processed data is then used to generate an Anki deck (`.apkg` file) based on a flexible YAML configuration that defines the card structure, fields, and styling.

## 🚀 Getting Started

### Prerequisites

- [Docker](https://www.docker.com/get-started) and [Docker Compose](https://docs.docker.com/compose/install/)
- Python 3.9+

### Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/aurcode/ankineitor.git
    cd ankineitor
    ```

2.  **Set up the environment:**
    You can run the application using Docker Compose, which is the recommended method.

    ```bash
    docker-compose up --build
    ```
This will build the Docker image and start the Streamlit application.

3.  **Access the application:**
Open your web browser and navigate to `http://localhost:8502`.

### New Django + React Pipeline UI (Incremental Migration)

The repository now includes a migration path that keeps Streamlit running while introducing:
- Django + DRF API for pipeline runs/results/category updates
- Django Channels websocket stream for live progress events
- Celery + Redis background execution for long-running runs
- React + TypeScript + React Flow UI for live graph visualization

Run all services:

```bash
docker-compose up --build app backend worker redis frontend
```

Service URLs:
- Streamlit (legacy): `http://localhost:8502`
- React pipeline UI: `http://localhost:5173`
- Django API: `http://localhost:8000`

Pipeline API endpoints:
- `POST /api/auth/token` (returns DRF token for username/password)
- `POST /api/pipeline/runs`
- `GET /api/pipeline/runs/{id}`
- `GET /api/pipeline/runs/{id}/results`
- `POST /api/pipeline/runs/{id}/add-category`
- `WS /ws/pipeline/runs/{id}`

Additional migrated tab APIs:
- Anki:
  - `GET /api/anki/presets`
  - `POST /api/anki/decks/generate` (creates async background job)
  - `GET /api/anki/decks/{artifact_id}/download`
- Flashcard Reviewer:
  - `GET /api/flashcards/saved-profiles`
  - `GET /api/flashcards/saved-files?profile_id=...`
  - `POST /api/flashcards/datasets/from-saved`
  - `POST /api/flashcards/datasets/upload`
  - `GET /api/flashcards/datasets/{dataset_id}`
  - `GET /api/flashcards/datasets/{dataset_id}/card?index=...`
- Word Extractor:
  - `POST /api/word-extractor/analyze` (creates async background job)
- Background jobs:
  - `GET /api/jobs?job_type=...&limit=...`
  - `GET /api/jobs/{job_id}`
  - `GET /api/jobs/{job_id}/events`
  - `POST /api/jobs/{job_id}/cancel`
  - `POST /api/jobs/{job_id}/retry`
  - `GET /api/jobs/{job_id}/results/csv` (for jobs that produced CSV output)
  - `WS /ws/jobs/{job_id}`
  - Job responses include `progress_ratio` and `status_text` for live progress UI.

Authentication notes:
- Django API endpoints now require `Authorization: Token <token>`.
- Websocket endpoints require `?token=<token>` query parameter.

### Run Tests Locally

```bash
pip install -r requirements.txt -r test_requirements.txt
pytest
```

Targeted migration tests:

```bash
pytest tests/test_web_pipeline_api.py tests/test_web_pipeline_ws.py tests/test_web_tabs_api.py
cd web/frontend && npm install && npm test
```

### Usage

1.  **Run the Pipeline**:
    - Navigate to the **"🚀 Run Pipeline"** tab.
    - Enter the words you want to process.
    - The pipeline will run, and the results will be cached.

2.  **Generate the Anki Deck**:
    - Go to the **"🤖 Anki Deck Generator"** tab.
    - Configure your deck settings.
    - Click the generate button to create the `.apkg` file.

3.  **Import into Anki**:
    - Download the generated `.apkg` file.
    - Open Anki and go to `File > Import` to add the new deck to your collection.

## 🔧 Configuration

The core of the deck generation is controlled by `app/configs/config.yaml`. This file allows you to define:
- The Anki card model (fields, templates).
- CSS styling for your cards.
- How media files (audio, images) are handled.
- Rules for generating tags.

By modifying this file, you can create highly customized Anki decks tailored to your specific learning style.

LLM language behavior is configured with environment variables:
- `LLM_SOURCE_LANGUAGE`: source language for non-Chinese words (`auto` by default).
- `LLM_TARGET_LANGUAGE`: primary target language for non-Chinese words (`english` by default).
- `LLM_SECONDARY_TARGET_LANGUAGE`: optional secondary target language (blank by default).

Chinese words are always processed with meanings in English and Spanish.
