
import os
from groq import Groq
from dotenv import load_dotenv
from Utils import MongoDBClient
load_dotenv()

class GroqAPIClient:
    def __init__(self, api_key=os.getenv('API_KEY')):
        self.client = Groq(api_key=api_key)

    def send_prompt(self, prompt: str, model: str = "llama3-8b-8192"):
        response = self.client.chat.completions.create(
            messages=[
                {"role": "user", "content": prompt}
            ],
            model=model
        )
        return response.choices[0].message.content

class ChineseWordProcessor:
    def __init__(self):
        self.mongo_client = MongoDBClient(collection_name='llm_predicts')
        self.api_client = GroqAPIClient()

    def process_word(self, word: str, previous_meaning: str = None):
        """
        Generates example sentences for the given Chinese word and improves the meaning.
        """
        existing_record = self.mongo_client.find_record(word)
        example_sentences = existing_record.get('example_sentences') if existing_record else None
        improved_meaning = existing_record.get('improved_meaning') if existing_record else None

        if example_sentences and improved_meaning:
            print(word, 'skipped')
            return {
                "hanzi": word,
                "example_sentences": example_sentences,
                "improved_meaning": improved_meaning
            }

        if not example_sentences:
            prompt_for_sentences = (
                f"Generate 3 example sentences using the Chinese word '{word}' in simplified Chinese."
                "Each sentence should be in simplified Chinese characters only."
                "Without explaining, without title, only the output. Format as follows:\n"
                "1: [sentence].\n"
                "2: [sentence].\n"
                "3: [sentence].\n"
            )
            example_sentences = self.api_client.send_prompt(prompt_for_sentences, model="llama3-groq-70b-8192-tool-use-preview")

        if not improved_meaning:
            if previous_meaning:
                prompt_meaning = (
                        f"Improve the following meaning of the Chinese word '{word}' in both English and Spanish. "
                        "The explanation should be concise and clear, giving only the necessary information without additional context. "
                        "Without explaining, without title, only the output. Format as follows:\n"
                        "english: [meaning]\n"
                        "spanish: [meaning]\n\n"
                        f"Current meaning:\n{previous_meaning}"
                    )

            else:
                prompt_meaning = (
                    f"Provide the essential meaning of the Chinese word '{word}' in both English and Spanish. "
                    "The explanation should be concise and clear, giving only the necessary information without additional context. "
                    "Without explaining, without title, only the output. Format as follows:\n"
                    "english: [meaning].\n"
                    "spanish: [meaning].\n"
                )

            improved_meaning = self.api_client.send_prompt(prompt_meaning)

        result = {
            "hanzi": word,
            "example_sentences": example_sentences,
            "improved_meaning": improved_meaning
        }

        self.mongo_client.insert_record(result, ['example_sentences', 'improved_meaning'])

        return result

    def process_words(self, words: list, previous_meanings: list = None):
        import pandas as pd
        """
        Processes a list of Chinese words and returns a DataFrame with results.
        """
        results = []
        for word in words:
            previous_meaning = previous_meanings.get(word) if previous_meanings else None
            result = self.process_word(word, previous_meaning)
            results.append(result)

        # Convert results to DataFrame
        df = pd.DataFrame(results)
        df[['hanzi', 'example_sentences', 'improved_meaning']]

        for idx, row in df.iterrows():
                sentences = row['example_sentences']
                parts = sentences.split('\n')
                for part in parts:
                    if part.startswith('1:'):
                        df.at[idx, 'sentence_1'] = part.strip()
                    elif part.startswith('2:'):
                        df.at[idx, 'sentence_2'] = part.strip()
                    elif part.startswith('3:'):
                        df.at[idx, 'sentence_3'] = part.strip()

                meanings = row['improved_meaning']
                parts = meanings.split('\n')
                for part in parts:
                    if part.startswith('english: '):
                        df.at[idx, 'meaning_english'] = part[len('english: '):].strip()
                    elif part.startswith('spanish: '):
                        df.at[idx, 'meaning_spanish'] = part[len('spanish: '):].strip()


        for idx, row in df.iterrows():
            if pd.isna(row['sentence_1']) or not row['sentence_1'].strip():
                print(f"Sentence 1 no asignada para el índice {idx} {row['hanzi']}.")
            if pd.isna(row['sentence_2']) or not row['sentence_2'].strip():
                print(f"Sentence 2 no asignada para el índice {idx} {row['hanzi']}.")
            if pd.isna(row['sentence_3']) or not row['sentence_3'].strip():
                print(f"Sentence 3 no asignada para el índice {idx} {row['hanzi']}.")
            if pd.isna(row['meaning_english']) or not row['meaning_english'].strip():
                print(f"Meaning (English) no asignado para el índice {idx} {row['hanzi']}.")
            if pd.isna(row['meaning_spanish']) or not row['meaning_spanish'].strip():
                print(f"Meaning (Spanish) no asignado para el índice {idx} {row['hanzi']}.")
        return df