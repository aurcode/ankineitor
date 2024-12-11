from typing import List, Dict, Optional
from dotenv import load_dotenv
from Utils import MongoDBClient
from loguru import logger
from groq import Groq
import pandas as pd
import os

load_dotenv()

class GroqAPIClient:
    def __init__(self, api_key: Optional[str] = None):
        """
        API Client to communicate with Groq API for generating examples and meanings.
        """
        self.api_key = api_key or os.getenv('API_KEY')
        self.client = Groq(api_key=self.api_key)

    def send_prompt(self, prompt: str, model: str = "llama-3.1-70b-versatile") -> str:
        """
        Sends a prompt to the Groq API and returns the response.
        """
        try:
            response = self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=model
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            # Log error or handle as needed
            print(f"Error sending prompt to Groq API: {e}")
            return ""

class ChineseWordProcessor:
    def __init__(
            self,
            mongo_client: MongoDBClient = MongoDBClient(collection_name='llm_predicts'),
            api_client: GroqAPIClient = GroqAPIClient(),
            max_retries: int = 3,
        ):
        self.mongo_client = mongo_client
        self.api_client = api_client
        self.max_retries = max_retries

    def process_word(self, word: str, previous_meaning: Optional[str] = None) -> Dict[str, str]:
        """
        Generates example sentences and improved meaning for a given Chinese word.
        """
        logger.info(f"Processing word: {word}")
        existing_record = self.mongo_client.find_record(word)

        example_sentences = existing_record.get('example_sentences') if existing_record else None
        improved_meaning = existing_record.get('improved_meaning') if existing_record else None

        if example_sentences and improved_meaning:
            logger.info(f"Skipping word {word} as it already has example sentences and meaning.")
            return {
                "hanzi": word,
                "example_sentences": example_sentences,
                "improved_meaning": improved_meaning
            }

        # Generate example sentences
        if not example_sentences:
            example_sentences = self._generate_example_sentences(word)

        # Generate improved meaning
        if not improved_meaning:
            improved_meaning = self._generate_improved_meaning(word, previous_meaning)

        # Save to DB
        result = {
            "hanzi": word,
            "example_sentences": example_sentences,
            "improved_meaning": improved_meaning
        }

        self.mongo_client.insert_record(result, ['example_sentences', 'improved_meaning'])
        logger.info(f"Word {word} processed successfully.")
        return result

    def _generate_example_sentences(self, word: str) -> str:
        """
        Generates example sentences for the word using Groq API.
        """
        prompt = (
            )
        return self.api_client.send_prompt(prompt)

    def _generate_example_sentences(self, word: str) -> str:
        """
        Generates example sentences for the word using Groq API.
        """
        prompt = (
            f"Generate 3 example sentences using the Chinese word '{word}' in simplified Chinese."
            " Each sentence should be in simplified Chinese characters only."
            " Without explaining, without title, only the output. Format as follows:\n"
            "1: [sentence].\n"
            "2: [sentence].\n"
            "3: [sentence].\n"
        )
        return self.api_client.send_prompt(prompt)

    def _generate_improved_meaning(self, word: str, previous_meaning: Optional[str]) -> str:
        """
        Generates or improves the meaning of the word in both English and Spanish.
        """
        if previous_meaning:
            prompt = (
                f"Improve the following meaning of the Chinese word '{word}' in both English and Spanish. "
                 "The explanation should be concise and clear, giving only the necessary information without additional context. "
                f"Current meaning:\n{previous_meaning}"
                 "Without explaining, without title, only the output. Format as follows:\n"
                 "english: [meaning]\nspanish: [meaning]\n"
            )
        else:
            prompt = (
                f"Provide the essential meaning of the Chinese word '{word}' in both English and Spanish. "
                 "The explanation should be concise and clear, giving only the necessary information without additional context. "
                 "Without explaining, without title, only the output. Format as follows:\n"
                 "english: [meaning].\n"
                 "spanish: [meaning].\n"
            )
        return self.api_client.send_prompt(prompt)

    def process_words(self, words: List[str], previous_meanings: Optional[dict] = None) -> pd.DataFrame:
        """
        Process a list of Chinese words and return the results in a DataFrame.
        """
        results = []
        for word in words:
            previous_meaning = previous_meanings.get(word) if previous_meanings else None
            result = self.process_word(word, previous_meaning)
            results.append(result)

        # Convert results to DataFrame
        df = pd.DataFrame(results)

        # Extract individual sentences and meanings
        df = self._extract_sentences_and_meanings(df)
        return df

    def _extract_sentences_and_meanings(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Extract individual example sentences and meanings into separate columns.
        """
        for idx, row in df.iterrows():
            sentences = row['example_sentences'].split('\n')
            for i, part in enumerate(sentences, start=1):
                if part.startswith(f"{i}:"):
                    df.at[idx, f'sentence_{i}'] = part[len(f"{i}:"):].strip()

            meanings = row['improved_meaning'].split('\n')
            for part in meanings:
                if part.startswith("english: "):
                    df.at[idx, 'meaning_english'] = part[len("english: "):].strip()
                elif part.startswith("spanish: "):
                    df.at[idx, 'meaning_spanish'] = part[len("spanish: "):].strip()

        # Handle missing values in 'sentence_1', 'sentence_2', 'sentence_3'
        self._handle_missing_values(df)
        return df

    def _handle_missing_values(self, df: pd.DataFrame):
        """
        Handle missing values in sentences and meanings.
        """
        for idx, row in df.iterrows():
            if pd.isna(row['sentence_1']) or not row['sentence_1'].strip() or \
               pd.isna(row['sentence_2']) or not row['sentence_2'].strip() or \
               pd.isna(row['sentence_3']) or not row['sentence_3'].strip():
                logger.warning(f"Missing example sentences for word {row['hanzi']} at index {idx}")
                self.mongo_client.update_field(row['hanzi'], "example_sentences", "")
            if pd.isna(row['meaning_english']) or not row['meaning_english'].strip() or \
               pd.isna(row['meaning_spanish']) or not row['meaning_spanish'].strip():
                logger.warning(f"Missing meaning for word {row['hanzi']} at index {idx}")
                self.mongo_client.update_field(row['hanzi'], "improved_meaning", "")