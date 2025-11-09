import os
from typing import List, Dict, Optional
from dotenv import load_dotenv
from loguru import logger
import pandas as pd

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

# Import the new SQLite client
from SQLiteClient import SQLiteClient

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


# --- Refactored ChineseWordProcessor ---


class LLMProcessor:
    """
    Processes Chinese words to find meanings and example sentences using
    LangChain and Groq, caching results in a SQLite database.
    """

    def __init__(
        self,
        db_client: SQLiteClient = SQLiteClient(),  # Use SQLiteClient
        api_key: Optional[str] = None,
        max_retries: int = 3,
    ):
        self.db_client = db_client  # Use the generic 'db_client'
        self.table_name = "llm_inference"  # Use 'table_name' for SQL
        self.field_name = "word"  # Key to find records
        self.max_retries = max_retries

        # 1. Initialize Groq Chat Model
        self.llm = ChatGroq(
            api_key=api_key or os.getenv("API_KEY"),
            model="llama-3.3-70b-versatile",
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

    def process_word(self, word: str) -> Optional[Dict[str, str]]:
        """
        Generates and saves structured data for a single Chinese word.
        Checks cache first, then calls API chains if data is missing.

        Returns a dictionary with all fields, or None if processing fails.
        """
        logger.info(f"Processing word: {word}")

        # 1. Check cache for *parsed* data
        try:
            existing_record = self.db_client.find_record(
                key=word,
                table_name=self.table_name,  # Updated to table_name
                field_name=self.field_name,
            )

            if (
                existing_record
                and existing_record.get("sentence_1")
                and existing_record.get("meaning_english")
            ):

                logger.info(f"Skipping word '{word}': Found complete data in cache.")
                return {
                    "word": word,
                    "sentence_1": existing_record.get("sentence_1"),
                    "sentence_2": existing_record.get("sentence_2"),
                    "sentence_3": existing_record.get("sentence_3"),
                    "meaning_english": existing_record.get("meaning_english"),
                    "meaning_spanish": existing_record.get("meaning_spanish"),
                }
        except Exception as e:
            logger.error(f"Error checking cache for word '{word}': {e}")

        logger.info(f"No cache found for '{word}', generating new data...")

        try:
            # 2. Generate new data using LangChain chains
            sentences_obj = self.sentence_chain.invoke({"word": word})
            meaning_obj = self.meaning_chain.invoke({"word": word})

            # 3. Combine results into a single dictionary
            result = {
                "word": word,
                **sentences_obj.model_dump(),
                "meaning_english": meaning_obj.english,
                "meaning_spanish": meaning_obj.spanish,
            }

            # 4. Save the *parsed* data to SQLite
            self.db_client.insert_record(
                record=result,
                columns=list(result.keys())[1:],
                table_name=self.table_name,  # Updated to table_name
                field_name=self.field_name,
            )

            logger.info(f"Word '{word}' processed and saved successfully.")
            return result

        except Exception as e:
            logger.error(f"Failed to process word '{word}' after retries: {e}")
            return None

    def process_words(self, words: List[str]) -> pd.DataFrame:
        """
        Process a list of Chinese words and return the results in a DataFrame.
        """
        results = []
        for word in words:
            if not word or not word.strip():
                logger.warning("Skipping empty word.")
                continue

            result = self.process_word(word)
            if result:
                results.append(result)

        if not results:
            logger.warning("No words were processed successfully.")
            return pd.DataFrame()

        df = pd.DataFrame(results)

        # Reorder columns
        expected_columns = [
            "word",
            "meaning_english",
            "meaning_spanish",
            "sentence_1",
            "sentence_2",
            "sentence_3",
        ]
        final_columns = [col for col in expected_columns if col in df.columns]

        return df[final_columns]

    def close_db(self):
        """Closes the database connection."""
        logger.info("Closing database connection.")
        self.db_client.close()


if __name__ == "__main__":
    from SQLiteClient import SQLiteClient
    from loguru import logger
    import os

    # Setup logging
    logger.add("logs/processing.log", rotation="10 MB")

    # Set DEBUG mode if needed
    os.environ["DEBUG"] = "true"

    db_client = None  # Define client outside try block
    try:
        # Initialize clients
        # This will create 'ankineitor.db' if it doesn't exist
        db_client = SQLiteClient(db_path="ankineitor.db")
        word_processor = LLMProcessor(
            db_client=db_client,
            api_key="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",
        )

        # List of words to process
        words_to_process = [
            "你好",
            "谢谢",
            "数据",
            "工程师",
            "你好",
        ]  # Duplicate to test caching

        logger.info("Starting word processing job...")

        # Process the words
        df = word_processor.process_words(words_to_process)

        if not df.empty:
            logger.info("Successfully processed words. DataFrame head:")
            print(df.head())

            # Save to CSV
            df.to_csv("chinese_words_processed.csv", index=False)
            logger.info("Results saved to 'chinese_words_processed.csv'")
        else:
            logger.warning("Job finished, but no data was returned.")

    except Exception as e:
        logger.critical(f"An unhandled error occurred: {e}")

    finally:
        # Ensure the database connection is always closed
        if db_client:
            db_client.close()
