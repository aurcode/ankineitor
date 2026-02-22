"""Manual demo entrypoint for running the transformation pipeline."""

from typing import List

from loguru import logger

from ankineitor.pipeline import TransformationPipeline
from ankineitor.pipeline.audio_creator import AudioCreator
from ankineitor.pipeline.db_client import SQLAlchemyClient
from ankineitor.pipeline.llm_transformation import LLMTransformation
from ankineitor.pipeline.transformations import (
    AudioTransformation,
    PinyinTransformation,
    TimestampTransformation,
    Transformation,
    TranslationTransformation,
)


def main() -> None:
    pipeline_db_client = SQLAlchemyClient(db_path="ankineitor_pipeline.db")
    llm_db_client = SQLAlchemyClient(db_path="ankineitor_llm_cache.db")
    audio_creator = AudioCreator(folder_name="./my_audio_files")

    transformations: List[Transformation] = [
        PinyinTransformation(),
        TranslationTransformation(lan_in="zh-CN", lan_out="es"),
        AudioTransformation(audio_creator=audio_creator),
        TimestampTransformation(),
        LLMTransformation(db_client=llm_db_client),
    ]
    pipeline = TransformationPipeline(
        db_client=pipeline_db_client,
        transformations=transformations,
        table_name="hanzi_processing",
    )
    words_to_process = ["你好", "谢谢", "数据", "工程师", "你好", "苹果", "熊猫"]

    try:
        df_results = pipeline.transform_data(words_to_process, dev_mode=False)
        print("\n--- Final Processed Data ---")
        print(df_results)
        df_results.to_csv("pipeline_results.csv", index=False)
        logger.info("Pipeline results saved to 'pipeline_results.csv'")

        logger.info("Adding 'HSK1' category to all processed words...")
        df_categorized = pipeline.transform_categories(df_results, category="HSK1")
        print("\n--- Final Categorized Data ---")
        print(df_categorized)
        df_categorized.to_csv("pipeline_results_categorized.csv", index=False)
        logger.info("Categorized results saved to 'pipeline_results_categorized.csv'")
    finally:
        pipeline_db_client.close()
        llm_db_client.close()


if __name__ == "__main__":
    main()
