import typer
from pathlib import Path
from rich.console import Console
import os

# Import from your independent libraries
from processing.TextExtractor import TextExtractor
from processing.TextProcessor import DataTransformer
from processing.LLMProcessor import ChineseWordProcessor

# Import the DeckGenerator from the local ankineitor module
# (Assuming you've placed the improved DeckGenerator class in this file)
from .ankineitor import DeckGenerator

app = typer.Typer(
    help="Ankineitor: A CLI tool to automatically generate Anki decks from documents."
)
console = Console()


@app.command()
def generate(
    file_path: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Path to the source file (e.g., PDF, TXT, PPTX).",
    ),
    config_path: Path = typer.Option(
        ...,
        "--config",
        "-c",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Path to the YAML configuration file for the deck.",
    ),
    deck_name: str = typer.Option(
        None,
        "--name",
        "-n",
        help="Name for the output .apkg file. Defaults to the input file's name.",
    ),
):
    """
    Extracts text from a file, processes it according to a config, and generates an Anki deck.
    """
    if deck_name is None:
        deck_name = file_path.stem

    try:
        console.print(
            f"🚀 Starting deck generation for '[cyan]{file_path.name}[/cyan]'..."
        )

        # 1. Instantiate services
        console.print(
            f"⚙️  Loading configuration from: '[yellow]{config_path.name}[/yellow]'"
        )
        deck_generator = DeckGenerator(config_path=str(config_path))
        config = deck_generator.config  # Access the loaded config

        text_extractor = TextExtractor(file_path)
        data_transformer = DataTransformer(config.get("transformer_config", {}))
        word_processor = ChineseWordProcessor(config.get("llm_config", {}))

        # 2. Text Extraction
        console.print("📄 Extracting text...")
        df = text_extractor.extract_text_to_dataframe()

        # 3. Data Transformation
        console.print("✨ Transforming data (Pinyin, Translations, Audio)...")
        df_transformed = data_transformer.transform_df(df)

        # 4. LLM Enrichment (if configured)
        if config.get("llm_config"):
            console.print("🧠 Enriching with LLM (Sentences & Meanings)...")
            df_final = word_processor.process_words(df_transformed)
        else:
            df_final = df_transformed

        # 5. Deck Generation
        console.print(f"📦 Generating Anki deck: '[cyan]{deck_name}.apkg[/cyan]'...")
        output_path = deck_generator.generate_deck_from_dataframe(df_final, deck_name)

        console.print(
            f"\n[bold green]✅ Success![/bold green] Deck saved to '{output_path}'"
        )

    except Exception as e:
        console.print(f"\n[bold red]An error occurred:[/bold red] {e}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
