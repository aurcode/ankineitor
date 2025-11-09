import os
from typing import List, Dict, Optional, Any
from dotenv import load_dotenv
from loguru import logger
import pandas as pd
from tqdm import tqdm

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    RetryCallState,
    RetryError,
)

# LangChain components
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

# Import the base class for inheritance
from transformations import Transformation

# Import the client, but we will type hint it generically
from db_client import SQLAlchemyClient

# Load environment variables
load_dotenv()

# --- Pydantic Models for Structured Output ---


class ExampleSentences(BaseModel):
    """Structured model for example sentences."""

    sentence_1: str = Field(description="The first example sentence.")
    sentence_2: str = Field(description="The second example sentence.")
    sentence_3: str = Field(description="The third example sentence.")


class WordMeaning(BaseModel):
    """Structured model for word meanings."""

    english: str = Field(description="The meaning of the word in English.")
    spanish: str = Field(description="The meaning of the word in Spanish.")


# --- Refactored LLMTransformation ---


class LLMTransformation(Transformation):
    """
    Processes Chinese words to find meanings and example sentences using
    LangChain and Groq, caching results in a separate database.
    This class now implements the Transformation interface.
    """

    def __init__(
        self,
        db_client: SQLAlchemyClient,  # Database client is now injected
        api_key: Optional[str] = None,
        max_retries: int = 3,
        table_name: str = "llm_inference",
    ):
        """
        Initializes the LLM Transformation.

        Args:
            db_client: A database client instance (e.g., SQLAlchemyClient)
                       for caching LLM results.
            api_key (Optional[str]): Groq API key. Defaults to env var.
            max_retries (int): Max retries for API calls.
            table_name (str): The specific table to use for LLM caching.
        """
        self.db_client = db_client
        self.table_name = table_name
        self.field_name = "word"
        self.max_retries = max_retries
        self.api_key = api_key or os.getenv("GROQ_API_KEY")

        if not self.api_key:
            logger.warning("GROQ_API_KEY not found in environment. Hardcoding key.")
            self.api_key = "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"

        # 1. Initialize Groq Chat Model
        self.llm = ChatGroq(
            api_key=self.api_key,
            model="llama-3.3-70b-versatile",  # Updated model
        )

        # 2. Setup Chain for Example Sentences
        self.sentence_parser = PydanticOutputParser(pydantic_object=ExampleSentences)
        self.sentence_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful assistant that provides structured data. "
                    "Respond *only* with the JSON object requested, do not add "
                    "any other text or explanations.",
                ),
                (
                    "human",
                    "使用简体中文字符生成 3 个示例句子，其中包含中文词 '{word}'。\n"
                    "每个句子应仅使用简体中文字符。\n"
                    "{format_instructions}",
                ),
            ]
        ).partial(format_instructions=self.sentence_parser.get_format_instructions())

        self.sentence_chain = self.sentence_prompt | self.llm | self.sentence_parser

        # 3. Setup Chain for Word Meanings
        self.meaning_parser = PydanticOutputParser(pydantic_object=WordMeaning)
        self.meaning_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful assistant that provides structured data. "
                    "Respond *only* with the JSON object requested, do not add "
                    "any other text or explanations.",
                ),
                (
                    "human",
                    "提供中文词 '{word}' 的基本含义，用英语和西班牙语描述。\n"
                    "解释应简明清晰，仅提供必要信息而不包含额外背景。\n"
                    "{format_instructions}",
                ),
            ]
        ).partial(format_instructions=self.meaning_parser.get_format_instructions())

        self.meaning_chain = self.meaning_prompt | self.llm | self.meaning_parser

    @property
    def column_name(self) -> str:
        """
        Returns a representative column name for this transformation.
        Note: This transformation adds *multiple* columns.
        """
        return "meaning_english"

    # We keep process_word as the core worker method
    def process_word(self, word: str) -> Optional[Dict[str, str]]:
        """
        Generates and saves structured data for a single Chinese word.
        Checks cache first, then calls API chains if data is missing.
        This is the internal logic for this transformation.

        Returns a dictionary with all fields, or None if processing fails.
        """
        logger.debug(f"LLMProcessing word: {word}")

        # 1. Check cache for *parsed* data
        try:
            existing_record = self.db_client.find_record(
                key=word,
                table_name=self.table_name,
                field_name=self.field_name,
            )

            if (
                existing_record
                and existing_record.get("sentence_1")
                and existing_record.get("meaning_english")
            ):
                logger.debug(
                    f"Skipping LLM for '{word}': Found complete data in cache."
                )
                return {
                    "word": word,
                    "sentence_1": existing_record.get("sentence_1"),
                    "sentence_2": existing_record.get("sentence_2"),
                    "sentence_3": existing_record.get("sentence_3"),
                    "meaning_english": existing_record.get("meaning_english"),
                    "meaning_spanish": existing_record.get("meaning_spanish"),
                }
        except Exception as e:
            logger.error(f"Error checking LLM cache for word '{word}': {e}")

        logger.debug(f"No LLM cache for '{word}', generating new data...")

        try:
            # 2. Generate new data using LangChain chains
            # We use tenacity for retries on the API calls
            @retry(
                stop=stop_after_attempt(self.max_retries),
                wait=wait_exponential(multiplier=1, min=2, max=10),
            )
            def get_sentences():
                return self.sentence_chain.invoke({"word": word})

            @retry(
                stop=stop_after_attempt(self.max_retries),
                wait=wait_exponential(multiplier=1, min=2, max=10),
            )
            def get_meaning():
                return self.meaning_chain.invoke({"word": word})

            sentences_obj = get_sentences()
            meaning_obj = get_meaning()

            # 3. Combine results into a single dictionary
            result = {
                "word": word,
                **sentences_obj.model_dump(),
                "meaning_english": meaning_obj.english,
                "meaning_spanish": meaning_obj.spanish,
            }

            # 4. Save the *parsed* data to SQLite via SQLAlchemy
            self.db_client.insert_record(
                record=result,
                columns=list(result.keys())[1:],
                table_name=self.table_name,
                field_name=self.field_name,
            )

            logger.debug(f"LLM data for '{word}' processed and saved.")
            return result

        except Exception as e:
            logger.error(f"Failed to process word '{word}' with LLM after retries: {e}")
            return None

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Applies the LLM transformation to a DataFrame.
        This method fulfills the Transformation interface.
        """
        logger.info("Applying LLM transformation...")
        if "word" not in df.columns:
            logger.error("LLMTransformation: DataFrame must have a 'word' column.")
            return df

        results = []
        # Use tqdm for progress, as this is the slowest step
        for word in tqdm(df["word"], desc="LLM Processing"):
            if not word or not word.strip():
                logger.warning("Skipping empty word.")
                results.append(None)
                continue

            # Call the internal worker method which handles
            # its own caching in the `llm_inference` table.
            result = self.process_word(word)
            results.append(result)

        # Create a new DataFrame from the results
        # Filter out None results before creating DataFrame
        valid_results = [r for r in results if r is not None]
        if not valid_results:
            logger.warning("LLMTransformation: No words were processed successfully.")
            return df  # Return original df

        df_results = pd.DataFrame(valid_results)

        # Define all columns this transformation creates
        llm_columns = [
            "sentence_1",
            "sentence_2",
            "sentence_3",
            "meaning_english",
            "meaning_spanish",
        ]

        # Select only the llm_columns that were actually generated
        # and the 'word' key
        generated_cols = [col for col in llm_columns if col in df_results.columns]
        if not generated_cols:
            logger.warning("LLMTransformation: No LLM columns in results.")
            return df

        final_llm_cols = ["word"] + generated_cols

        # Merge results back into the original DataFrame
        # Use 'how="left"' to preserve all original rows and 'word' as the key
        # Use suffixes to identify any potential column clashes (though unlikely)
        df = pd.merge(
            df,
            df_results[final_llm_cols],
            on="word",
            how="left",
            suffixes=("", "_llm"),
        )

        # Drop duplicate 'word' entries that merge might create if there are
        # upstream duplicates, keeping the first processed instance.
        df = df.drop_duplicates(subset=["word"]).reset_index(drop=True)

        logger.info("LLM transformation applied successfully.")
        return df
