from fastapi import FastAPI
from api import *
import logging
import os
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Deck Generator API", description="API to generate Anki decks.", version="0.1.0")

# Register routers
app.include_router(ankineitor_router, prefix="/api/v1", tags=["Deck Generator"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)