import os
from db_client import SQLAlchemyClient
from audio_creator import AudioCreator
from transformations import (
    Transformation,
    PinyinTransformation,
    TranslationTransformation,
    AudioTransformation,
    TimestampTransformation,
)
from llm_transformation import LLMTransformation
from pipeline import TransformationPipeline
from loguru import logger
from typing import List

# --- Setup Logging ---
# Ensure logs directory exists
os.makedirs("logs", exist_ok=True)
logger.add("logs/pipeline.log", rotation="10 MB", level="INFO")
logger.add("logs/pipeline_debug.log", rotation="10 MB", level="DEBUG", enqueue=True)


if __name__ == "__main__":
    logger.info("--- Starting New Pipeline Job ---")

    # 1. Setup Dependencies

    # This client manages the *main pipeline* cache
    # It stores the *final* processed data (pinyin, translation, audio path, etc.)
    pipeline_db_client = SQLAlchemyClient(db_path="ankineitor_pipeline.db")

    # This client *only* manages the cache for *LLM inference*
    # This separation is good: it caches raw API results.
    llm_db_client = SQLAlchemyClient(db_path="ankineitor_llm_cache.db")

    # This handles audio file creation
    audio_creator = AudioCreator(folder_name="./my_audio_files")

    # 2. Define the pipeline transformations
    # We can now add LLMTransformation just like any other
    my_transformations: List[Transformation] = [
        PinyinTransformation(),
        TranslationTransformation(lan_in="zh-CN", lan_out="es"),
        AudioTransformation(audio_creator=audio_creator),
        TimestampTransformation(),
        # Add the refactored LLMTransformation
        # We inject its dedicated database client
        LLMTransformation(db_client=llm_db_client),
    ]

    # 3. Initialize the pipeline
    # We pass the *pipeline's* db client here
    pipeline = TransformationPipeline(
        db_client=pipeline_db_client,
        transformations=my_transformations,
        table_name="hanzi_processing",  # Main table for processed words
    )

    # 4. Define words and run the pipeline
    words_to_process = [
        "你好",  # Hello
        "谢谢",  # Thank you
        "数据",  # Data
        "工程师",  # Engineer
        "你好",  # Duplicate (tests pipeline caching)
        "苹果",  # Apple
        "熊猫",  # Panda (New)
    ]

    try:
        # dev_mode=True processes only the first 20 words
        df_results = pipeline.transform_data(words_to_process, dev_mode=False)

        print("\n--- Final Processed Data ---")
        print(df_results)

        # Save results to CSV
        df_results.to_csv("pipeline_results.csv", index=False)
        logger.info("Pipeline results saved to 'pipeline_results.csv'")

        # 5. (Optional) Add categories to the results
        # This step runs *after* the main pipeline processing
        logger.info("Adding 'HSK1' category to all processed words...")
        df_categorized = pipeline.transform_categories(df_results, category="HSK1")

        print("\n--- Final Categorized Data ---")
        print(df_categorized)
        df_categorized.to_csv("pipeline_results_categorized.csv", index=False)
        logger.info("Categorized results saved to 'pipeline_results_categorized.csv'")

    except Exception as e:
        logger.critical(f"An unhandled error occurred in the pipeline: {e}")

    finally:
        # 6. Close DB connections
        pipeline_db_client.close()
        llm_db_client.close()
        logger.info("Database connections closed. Job complete.")
        print("\nJob complete. Check logs/pipeline.log for details.")
