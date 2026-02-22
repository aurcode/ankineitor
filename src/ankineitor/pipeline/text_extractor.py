import os
import io
import re
import hashlib
from typing import Dict, List, Set, Tuple, Type
from dotenv import load_dotenv
import pandas as pd
from loguru import logger

JIEBA_AVAILABLE = True
try:
    import jieba.posseg as pseg
except ModuleNotFoundError:
    JIEBA_AVAILABLE = False
    pseg = None

PYPDF_AVAILABLE = True
try:
    from pypdf import PdfReader
except ModuleNotFoundError:
    PYPDF_AVAILABLE = False
    PdfReader = None

PDF2IMAGE_AVAILABLE = True
try:
    from pdf2image import convert_from_bytes
except ModuleNotFoundError:
    PDF2IMAGE_AVAILABLE = False
    convert_from_bytes = None

PYTESSERACT_AVAILABLE = True
try:
    import pytesseract
except ModuleNotFoundError:
    PYTESSERACT_AVAILABLE = False
    pytesseract = None

# --- Unstructured Imports (optional at runtime) ---
UNSTRUCTURED_AVAILABLE = True
try:
    from unstructured.partition.auto import partition
    from unstructured.cleaners.core import (
        clean,
        clean_extra_whitespace,
        clean_bullets,
        clean_dashes,
        replace_unicode_quotes,
    )
    from unstructured.documents.elements import Header, Footer, PageNumber, Element
except ModuleNotFoundError:
    UNSTRUCTURED_AVAILABLE = False
    partition = None
    Header = Footer = PageNumber = object
    Element = object

    def clean(text, bullets=False, dashes=False, extra_whitespace=False):
        return text

    def clean_extra_whitespace(text):
        return text

    def clean_bullets(text):
        return text

    def clean_dashes(text):
        return text

    def replace_unicode_quotes(text):
        return text

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
        self.extraction_errors: Dict[str, str] = {}

        # Categories of elements to ignore during extraction
        self.junk_category_names: Set[str] = {"Header", "Footer", "PageNumber"}
        self.junk_element_types: Tuple[Type[Element], ...] = ()
        if UNSTRUCTURED_AVAILABLE:
            self.junk_element_types = (Header, Footer, PageNumber)

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

    def _is_junk_element(self, element: Element) -> bool:
        """Checks if an unstructured element is ignorable noise."""
        if self.junk_element_types and isinstance(element, self.junk_element_types):
            return True
        category = getattr(element, "category", None)
        return category in self.junk_category_names

    def extract_content(self, min_phrase_len: int = 6):
        """
        Parses all uploaded files using 'unstructured', cleans the text,
        and populates 'self.text' and 'self.phrases'.
        """
        logger.info(f"Extracting content from {len(self.uploaded_files)} file(s)...")
        self.extraction_errors = {}

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
        if not UNSTRUCTURED_AVAILABLE or partition is None:
            raise RuntimeError(
                "File extraction requires the 'unstructured' package. "
                "Install project dependencies first."
            )

        cleaned_phrases: List[str] = []
        strategy = "hi_res" if self.dev_enabled else "auto"

        for file_name, file_content in self.uploaded_files.items():
            logger.debug(f"Partitioning file: {file_name} with strategy '{strategy}'")
            file_extension = os.path.splitext(file_name)[1].lower()
            try:
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
                    if self._is_junk_element(el):
                        continue

                    cleaned_text = self._clean_element_text(el.text)

                    # Add to phrases if it meets length and content requirements
                    if (
                        cleaned_text
                        and len(cleaned_text) >= min_phrase_len
                        and self.chinese_regex.search(cleaned_text)
                    ):

                        # Keep duplicates to preserve true downstream frequency counts.
                        cleaned_phrases.append(cleaned_text)

            except Exception as e:
                # Fallback for PDFs when unstructured's PDF stack is unavailable.
                if file_extension == ".pdf":
                    if self._try_pdf_text_fallback(file_name, file_content, min_phrase_len, cleaned_phrases):
                        continue

                logger.error(f"Error partitioning file '{file_name}': {e}")
                if file_name not in self.extraction_errors:
                    self.extraction_errors[file_name] = str(e)
                continue

        self.phrases = sorted(cleaned_phrases, key=len, reverse=True)
        self.text = "。".join(self.phrases)  # Join with a Chinese full stop
        logger.info(f"Content extracted. Found {len(self.phrases)} phrases.")

    def _try_pdf_text_fallback(
        self,
        file_name: str,
        file_content: bytes,
        min_phrase_len: int,
        cleaned_phrases: List[str],
    ) -> bool:
        """
        Attempts fallback extraction using pypdf when unstructured PDF parsing fails.
        Returns True if fallback succeeded enough to continue processing.
        """
        if not PYPDF_AVAILABLE or PdfReader is None:
            return False

        try:
            reader = PdfReader(io.BytesIO(file_content))
            pages = reader.pages[:3] if self.dev_enabled else reader.pages
            extracted_chunks: List[str] = []

            for page in pages:
                page_text = page.extract_text() or ""
                if page_text.strip():
                    extracted_chunks.append(page_text)

            if not extracted_chunks:
                return self._try_pdf_ocr_fallback(
                    file_name=file_name,
                    file_content=file_content,
                    min_phrase_len=min_phrase_len,
                    cleaned_phrases=cleaned_phrases,
                )

            fallback_text = "\n".join(extracted_chunks)
            cleaned_text = self._clean_element_text(fallback_text)
            if (
                cleaned_text
                and len(cleaned_text) >= min_phrase_len
                and self.chinese_regex.search(cleaned_text)
            ):
                cleaned_phrases.append(cleaned_text)
                logger.warning(
                    f"Used pypdf fallback extraction for '{file_name}' due to unstructured PDF parsing error."
                )
                return True

            return self._try_pdf_ocr_fallback(
                file_name=file_name,
                file_content=file_content,
                min_phrase_len=min_phrase_len,
                cleaned_phrases=cleaned_phrases,
            )
        except Exception as fallback_error:
            logger.warning(
                f"pypdf fallback failed for '{file_name}': {fallback_error}. "
                "Attempting OCR fallback."
            )
            return self._try_pdf_ocr_fallback(
                file_name=file_name,
                file_content=file_content,
                min_phrase_len=min_phrase_len,
                cleaned_phrases=cleaned_phrases,
            )

    def _try_pdf_ocr_fallback(
        self,
        file_name: str,
        file_content: bytes,
        min_phrase_len: int,
        cleaned_phrases: List[str],
    ) -> bool:
        """
        OCR fallback for image-based PDFs using pdf2image + pytesseract.
        Returns True if OCR produced Chinese text suitable for segmentation.
        """
        if (
            not PDF2IMAGE_AVAILABLE
            or convert_from_bytes is None
            or not PYTESSERACT_AVAILABLE
            or pytesseract is None
        ):
            self.extraction_errors[file_name] = (
                "PDF text extraction failed and OCR fallback dependencies are missing "
                "(install pdf2image + pytesseract)."
            )
            return False

        try:
            first_page = 1
            last_page = 3 if self.dev_enabled else None
            images = convert_from_bytes(
                file_content,
                dpi=250,
                first_page=first_page,
                last_page=last_page,
            )
            if not images:
                self.extraction_errors[file_name] = (
                    "OCR fallback could not render PDF pages for text extraction."
                )
                return False

            ocr_chunks: List[str] = []
            for image in images:
                text = pytesseract.image_to_string(image, lang="chi_sim+chi_tra+eng")
                if text and text.strip():
                    ocr_chunks.append(text)

            if not ocr_chunks:
                self.extraction_errors[file_name] = (
                    "OCR fallback found no readable text in PDF pages."
                )
                return False

            ocr_text = self._clean_element_text("\n".join(ocr_chunks))
            if (
                ocr_text
                and len(ocr_text) >= min_phrase_len
                and self.chinese_regex.search(ocr_text)
            ):
                cleaned_phrases.append(ocr_text)
                logger.warning(
                    f"Used OCR fallback extraction for '{file_name}' due to PDF parser limitations."
                )
                return True

            self.extraction_errors[file_name] = (
                "OCR fallback extracted text but no Chinese content was detected."
            )
            return False
        except Exception as ocr_error:
            self.extraction_errors[file_name] = f"OCR fallback failed: {ocr_error}"
            return False

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
        if not JIEBA_AVAILABLE or pseg is None:
            raise RuntimeError(
                "Word segmentation requires the 'jieba' package. "
                "Install project dependencies first."
            )

        logger.info("Segmenting Chinese text with 'jieba'...")
        # Find all continuous blocks of Chinese text
        chinese_text_blocks = self.chinese_regex.findall(self.text)
        full_chinese_text = "。".join(chinese_text_blocks)

        # Segment the text using 'jieba' with part-of-speech tagging
        # use_paddle=True can fail if paddle dependencies are not installed.
        try:
            seg_list = list(pseg.cut(full_chinese_text, use_paddle=True))
        except Exception as exc:
            logger.warning(
                "Paddle segmentation unavailable, falling back to default jieba mode: "
                f"{exc}"
            )
            seg_list = list(pseg.cut(full_chinese_text, use_paddle=False))

        # --- Refactored Pandas Logic ---

        # 1. Create initial DataFrame
        df = pd.DataFrame(seg_list, columns=["word", "part"])

        # 2. Filter out punctuation and empty strings
        df["word"] = df["word"].astype(str)
        df = df[df["word"].str.strip() != ""]
        df = df[df["word"].apply(lambda word: bool(self.chinese_regex.search(word)))]

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
