"""Manual demo entrypoint for file extraction and segmentation."""

from loguru import logger

from ankineitor.pipeline.text_extractor import TextExtractor


def main() -> None:
    logger.add("logs/file_processing.log", rotation="10 MB")
    file_paths = ["./试试.pdf"]
    uploaded_files = TextExtractor.read_files_to_uploaded(file_paths)

    if not uploaded_files:
        logger.error("No files were loaded. Check file paths.")
        return

    extractor = TextExtractor(uploaded_files, dev_enabled=True)
    extractor.extract_content()

    df = extractor.separated_chinese_characters()
    if not df.empty:
        logger.info(f"Successfully segmented {len(df)} unique words.")
        print("--- Top 10 Most Frequent Words ---")
        print(df.head(10))
    else:
        logger.warning("No words were segmented.")

    phrases = extractor.phrases
    if phrases:
        logger.info(f"Found {len(phrases)} phrases/chunks.")
        print("\n--- Longest Extracted Phrase ---")
        print(phrases[0])


if __name__ == "__main__":
    main()
