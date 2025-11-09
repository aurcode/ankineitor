# --- main.py ---
# from db_client import SQLAlchemyClient  # <-- Your client
# from transformations import (
#     PinyinTransformation, TranslationTransformation,
#     AudioTransformation, TimestampTransformation
# )
# from audio_creator import AudioCreator
# from pipeline import TransformationPipeline

# --- For this example, I'll put all imports here ---
from db_client import SQLAlchemyClient
from SQLiteClient import SQLiteClient  # This is for LLM
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


if __name__ == "__main__":
    logger.add("logs/pipeline.log", rotation="10 MB")

    # 1. Setup Dependencies
    db_client = SQLAlchemyClient(db_path="ankineitor.db")
    audio_creator = AudioCreator(folder_name="./my_audio_files")

    db_client_0 = SQLiteClient(db_path="ankineitor_0.db")

    # 2. Define the pipeline
    # Just add the transformations you want!
    my_transformations: List[Transformation] = [
        PinyinTransformation(),
        TranslationTransformation(lan_in="zh-CN", lan_out="es"),
        AudioTransformation(audio_creator=audio_creator),
        TimestampTransformation(),
        # LLMTransformation(db_client=db_client_0),
    ]

    # 3. Initialize the pipeline
    pipeline = TransformationPipeline(
        db_client=db_client, transformations=my_transformations
    )

    # 4. Run the pipeline
    words_to_process = ["你好", "谢谢", "数据", "工程师", "你好", "苹果"]

    # dev_mode=True processes only the first 20 words
    df_results = pipeline.transform_data(words_to_process, dev_mode=False)

    print("--- Final Processed Data ---")
    print(df_results)

    # 5. (Optional) Add categories to the results
    df_categorized = pipeline.transform_categories(df_results, category="HSK1")

    print("\n--- Final Categorized Data ---")
    print(df_categorized)

    # 6. Close DB connection
    db_client.close()
    logger.info("Job complete.")
