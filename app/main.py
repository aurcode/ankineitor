from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict
import pandas as pd
import logging
from services.Ankineitor import DeckGenerator  # Ensure your DeckGenerator class is in a module named 'deck_generator'

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Deck Generator API", description="API to generate Anki decks.", version="0.1.0")

class ModelField(BaseModel):
    name: str

class ModelTemplate(BaseModel):
    name: str
    qfmt: str
    afmt: str

class ConfigBasics(BaseModel):
    id: int
    deck_title: str
    model_name: str
    filename: str
    note_type: str

class ConfigTemplates(BaseModel):
    main: List[ModelTemplate]
    css: str

class Config(BaseModel):
    basics: ConfigBasics
    model_fields: List[ModelField]
    model_templates: ConfigTemplates
    model_builder: List[str]

class DeckRequest(BaseModel):
    dataframe: List[Dict]
    config: Config

def validate_config(config: Config):
    """Validate the configuration format."""
    required_keys = {'basics', 'model_fields', 'model_templates', 'model_builder'}
    basics_keys = {'id', 'deck_title', 'model_name', 'filename', 'note_type'}
    template_keys = {'main', 'css'}

    # Check top-level keys
    if not isinstance(config, dict):
        return False, "Config must be a dictionary."
    if not required_keys.issubset(config.keys()):
        return False, f"Config must include keys: {required_keys}."

    # Check 'basics' structure
    if not basics_keys.issubset(config['basics']):
        return False, f"'basics' must include keys: {basics_keys}."

    # Check 'model_fields'
    if not isinstance(config['model_fields'], list) or not all(isinstance(field, dict) and 'name' in field for field in config['model_fields']):
        return False, "'model_fields' must be a list of dictionaries with a 'name' key."

    # Check 'model_templates'
    if not isinstance(config['model_templates'], dict) or not template_keys.issubset(config['model_templates']):
        return False, f"'model_templates' must include keys: {template_keys}."
    if not isinstance(config['model_templates']['main'], list):
        return False, "'model_templates.main' must be a list of dictionaries."
    if not isinstance(config['model_templates']['css'], str):
        return False, "'model_templates.css' must be a string."

    # Check 'model_builder'
    if not isinstance(config['model_builder'], list) or not all(isinstance(item, str) for item in config['model_builder']):
        return False, "'model_builder' must be a list of strings."

    return True, "Config is valid."

@app.post("/generate_deck", summary="Generate Anki Deck", description="Generate an Anki deck from a DataFrame and configuration.")
async def generate_deck(request: DeckRequest):
    """Endpoint to generate an Anki deck."""
    try:
        # Convert request to DataFrame and Config
        df = pd.DataFrame(request.dataframe)
        config = request.config

        # Validate config format
        is_valid, validation_message = validate_config(config.dict())
        if not is_valid:
            raise HTTPException(status_code=400, detail=validation_message)

        # Generate the deck
        generator = DeckGenerator(df, config.dict()).generate_deck()
        filepath = generator.get_filepath()

        return {"message": "Deck generated successfully.", "filepath": filepath}

    except Exception as e:
        logger.error(f"Error generating deck: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
