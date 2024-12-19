from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Dict
import pandas as pd
from services.Ankineitor import DeckGenerator
import os
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/ankineitor")

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

@router.post("/generate_deck", summary="Generate Anki Deck", description="Generate an Anki deck from a DataFrame and configuration.")
async def generate_deck(request: DeckRequest):
    """Endpoint to generate an Anki deck."""
    try:
        df = pd.DataFrame(request.dataframe)
        config = request.config.dict()

        # Generate the deck
        generator = DeckGenerator(df, config).generate_deck()
        filepath = generator.get_filepath()

        return {"message": "Deck generated successfully.", "download_link": f"/api/v1/download_deck?filepath={filepath}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/download_deck", summary="Download Anki Deck", description="Download the generated Anki deck by providing the file path.")
async def download_deck(filepath: str):
    """Endpoint to download the generated Anki deck."""
    filepath = '/opt/output/' + filepath if os.getenv('DOCKER') else filepath
    try:
        return FileResponse(filepath, media_type="application/octet-stream", filename=filepath.split("/")[-1])
    except Exception as e:
        raise HTTPException(status_code=500, detail="Could not download the file.")
