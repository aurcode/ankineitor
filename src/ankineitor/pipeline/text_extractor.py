import os
import io
import re
import hashlib
from typing import List, Union, Dict, Set
from dotenv import load_dotenv
import pandas as pd
import jieba.posseg as pseg
from loguru import logger

# --- Unstructured Imports ---
from unstructured.partition.auto import partition
from unstructured.cleaners.core import (
    clean,
    clean_extra_whitespace,
    clean_bullets,
    clean_dashes,
    replace_unicode_quotes,
)
from unstructured.documents.elements import Header, Footer, PageNumber, Element

# Load environment variables
load_dotenv()


class TextExtractor:
    """
    Handles file parsing, text extraction, and Chinese word segmentation
    using the 'unstructured' library and 'jieba'.
    """

    def __init__(self, uploaded_files: Dict[str, bytes], dev_enabled: bool = False):
        """
        Initializes the extractor with a dictionary of file names and their byte content.

        Args:
            uploaded_files: A dictionary mapping file_name (str) to file_content (bytes).
            dev_enabled: If True, limits processing for testing (e.g., first 3 pages).
        """
        self.dev_enabled = dev_enabled
        self.uploaded_files = uploaded_files
        self.text: str = ""  # All cleaned text, joined together.
        self.phrases: List[str] = []  # List of individual cleaned text chunks.

        # Categories of elements to ignore during extraction
        self.junk_categories: Set[Element] = {Header, Footer, PageNumber}

        # Pre-compile regex for finding Chinese characters
        self.chinese_regex = re.compile(r"[\u4E00-\u9FFF]+")

    def _get_content_hash(self) -> str:
        """
        Generates a single SHA-256 hash for all uploaded file content.
        This is a reliable key for caching.
        """
        hasher = hashlib.sha256()
        # Sort by filename to ensure consistent hash order
        for file_name in sorted(self.uploaded_files.keys()):
            hasher.update(self.uploaded_files[file_name])
        return hasher.hexdigest()

    def _clean_element_text(self, text: str) -> str:
        """
        Applies a series of 'unstructured' cleaners to a single text chunk.
        """
        text = clean(text, bullets=False, dashes=False, extra_whitespace=False)
        text = clean_extra_whitespace(text)
        text = clean_bullets(text)
        text = clean_dashes(text)
        text = replace_unicode_quotes(text)
        return text.strip()

    def extract_content(self, min_phrase_len: int = 6):
        """
        Parses all uploaded files using 'unstructured', cleans the text,
        and populates 'self.text' and 'self.phrases'.
        """
        logger.info(f"Extracting content from {len(self.uploaded_files)} file(s)...")

        # --- Handle Pasted Text Directly ---
        # If the only input is pasted text, process it without chunking/filtering.
        if list(self.uploaded_files.keys()) == ["pasted_text.txt"]:
            pasted_content = self.uploaded_files["pasted_text.txt"].decode("utf-8").strip()
            if self.chinese_regex.search(pasted_content):
                self.text = pasted_content
                self.phrases = [pasted_content]
                logger.info("Content extracted directly from pasted text.")
                return  # Skip file-based extraction
            else:
                logger.warning("Pasted text contains no Chinese characters.")
                return

        # --- Handle File Uploads ---
        cleaned_phrases: Set[str] = set()
        strategy = "hi_res" if self.dev_enabled else "auto"

        for file_name, file_content in self.uploaded_files.items():
            logger.debug(f"Partitioning file: {file_name} with strategy '{strategy}'")
            try:
                file_extension = os.path.splitext(file_name)[1].lower()

                # Handle text files by decoding them first
                if file_extension == ".txt":
                    elements = partition(
                        text=file_content.decode("utf-8"),
                        file_filename=file_name,
                        strategy=strategy,
                    )
                # Handle binary files (PDF, DOCX, etc.) with a file-like object
                else:
                    file_io = io.BytesIO(file_content)
                    elements = partition(
                        file=file_io,
                        file_filename=file_name,
                        strategy=strategy,
                        # For dev mode, 'hi_res' strategy respects max_pages
                        max_pages=3 if self.dev_enabled else None,
                    )

                for el in elements:
                    # Skip junk elements
                    if el.category in self.junk_categories:
                        continue

                    cleaned_text = self._clean_element_text(el.text)

                    # Add to phrases if it meets length and content requirements
                    if (
                        cleaned_text
                        and len(cleaned_text) >= min_phrase_len
                        and self.chinese_regex.search(cleaned_text)
                    ):

                        cleaned_phrases.add(cleaned_text)

            except Exception as e:
                logger.error(f"Error partitioning file '{file_name}': {e}")
                continue

        self.phrases = sorted(list(cleaned_phrases), key=len, reverse=True)
        self.text = "。".join(self.phrases)  # Join with a Chinese full stop
        logger.info(f"Content extracted. Found {len(self.phrases)} unique phrases.")

    def separated_chinese_characters(self) -> pd.DataFrame:
        """
        Segments the extracted Chinese text into words, parts of speech,
        and frequencies using 'jieba'.

        Returns:
            A pandas DataFrame with columns: ['word', 'part', 'frequency'],
            sorted by frequency.
        """
        if not self.text:
            logger.warning("No text extracted. Call extract_content() first.")
            return pd.DataFrame(columns=["word", "part", "frequency"])

        logger.info("Segmenting Chinese text with 'jieba'...")
        # Find all continuous blocks of Chinese text
        chinese_text_blocks = self.chinese_regex.findall(self.text)
        full_chinese_text = "。".join(chinese_text_blocks)

        # Segment the text using 'jieba' with part-of-speech tagging
        # use_paddle=True enables paddle mode for better accuracy
        seg_list = list(pseg.cut(full_chinese_text, use_paddle=True))

        # --- Refactored Pandas Logic ---

        # 1. Create initial DataFrame
        df = pd.DataFrame(seg_list, columns=["word", "part"])

        # 2. Filter out punctuation and empty strings
        df = df[~df["word"].isin(["。", "，", " "])]  # Add more punctuation if needed
        df = df[df["word"].str.strip() != ""]

        if df.empty:
            logger.warning("No valid Chinese words found after segmentation.")
            return pd.DataFrame(columns=["word", "part", "frequency"])

        # 3. Group by word, aggregate parts (unique) and frequency (count)
        # This is far more efficient than the original merge logic.
        agg_df = (
            df.groupby("word")
            .agg(
                # Get a sorted list of unique parts-of-speech
                part=("part", lambda x: ", ".join(sorted(list(set(x))))),
                # Get the count of the word
                frequency=("word", "count"),
            )
            .reset_index()
        )

        # 4. Sort by frequency and return
        return agg_df.sort_values(by="frequency", ascending=False).reset_index(
            drop=True
        )

    @staticmethod
    def read_files_to_uploaded(file_paths: List[str]) -> Dict[str, bytes]:
        """
        Utility static method to read files from local paths into the
        dictionary format required by the constructor.
        """
        uploaded_files = {}
        for file_path in file_paths:
            try:
                with open(file_path, "rb") as file:
                    uploaded_files[os.path.basename(file_path)] = file.read()
            except FileNotFoundError:
                logger.error(f"File not found: {file_path}")
            except Exception as e:
                logger.error(f"Error reading file '{file_path}': {e}")
        return uploaded_files


if __name__ == "__main__":
    # Add a log sink for better output
    logger.add("logs/file_processing.log", rotation="10 MB")

    # 1. Use the static helper to read local files
    # Replace with the path to your test PDF
    file_paths = ["./试试.pdf"]
    uploaded_files = TextExtractor.read_files_to_uploaded(file_paths)

    if uploaded_files:
        # 2. Initialize the extractor
        # Set dev_enabled=True for a quick test (processes ~3 pages)
        # Set dev_enabled=False for full processing
        extractor = TextExtractor(uploaded_files, dev_enabled=True)

        # 3. Run the extraction
        # This populates extractor.text and extractor.phrases
        extractor.extract_content()

        # 4. Get the segmented words DataFrame
        df = extractor.separated_chinese_characters()

        if not df.empty:
            logger.info(f"Successfully segmented {len(df)} unique words.")
            print("--- Top 10 Most Frequent Words ---")
            print(df.head(10))
        else:
            logger.warning("No words were segmented.")

        # 5. You can also access the extracted phrases
        phrases = extractor.phrases
        if phrases:
            logger.info(f"Found {len(phrases)} unique phrases/chunks.")
            print("\n--- Longest Extracted Phrase ---")
            print(phrases[0])  # They are sorted by length
    else:
        logger.error("No files were loaded. Check file paths.")
