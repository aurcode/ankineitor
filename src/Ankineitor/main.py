from pathlib import Path
import pandas as pd
from loguru import logger
from deck_generator import DeckGenerator

def main():
    """
    Main function to run the deck generation process.
    """
    # Define paths based on the project structure
    CONFIG_PATH = Path("config.yaml")
    DATA_PATH = Path("data/vocabulary.csv")
    OUTPUT_DIR = Path("output/")
    DECK_NAME = "My English Vocabulary"

    # --- Pre-run Checks ---
    if not CONFIG_PATH.exists():
        logger.error(f"Configuration file not found at '{CONFIG_PATH}'. Exiting.")
        return

    if not DATA_PATH.exists():
        logger.error(f"Data file not found at '{DATA_PATH}'. Exiting.")
        return

    # --- Deck Generation ---
    try:
        # 1. Load the data from CSV into a pandas DataFrame
        logger.info(f"Reading data from {DATA_PATH}...")
        df = pd.read_csv(DATA_PATH)
        df = df.astype(object).where(pd.notnull(df), None) # Replace NaN with None

        # 2. Initialize the DeckGenerator with the config file
        generator = DeckGenerator(config_path=CONFIG_PATH)

        # 3. Generate the deck
        generator.generate_deck(
            df=df,
            deck_name=DECK_NAME,
            output_path=OUTPUT_DIR,
            strict=False  # Set to True to fail if media is missing
        )

    except Exception as e:
        logger.error(f"An unexpected error occurred during deck generation: {e}")

if __name__ == "__main__":
    main()
