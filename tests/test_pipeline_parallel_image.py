"""Tests for pipeline-level parallel image generation behavior."""

from threading import Event
import time

import pandas as pd

import ankineitor.pipeline.pipeline as pipeline_module
from ankineitor.pipeline.pipeline import TransformationPipeline
from ankineitor.pipeline.transformations import Transformation


class FakeDBClient:
    def __init__(self):
        self.inserted_records = []

    def find_many_by_field(self, keys, table_name, field_name):
        return []

    def insert_many_records(self, records, table_name):
        self.inserted_records.extend(records)


class DummyTextLLMTransformation(Transformation):
    def __init__(self, image_started: Event):
        self.image_started = image_started
        self.saw_image_started = False

    @property
    def column_name(self) -> str:
        return "sentence_1"

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        self.saw_image_started = self.image_started.wait(timeout=0.2)
        time.sleep(0.05)
        output = df.copy()
        output["sentence_1"] = output["word"].astype(str).map(lambda w: f"Sentence for {w}")
        return output


class DummyImageLLMTransformation(Transformation):
    def __init__(self, image_started: Event, max_workers: int = 1):
        self.image_started = image_started
        self.max_workers = max_workers

    @property
    def column_name(self) -> str:
        return "picture"

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        self.image_started.set()
        time.sleep(0.05)
        output = df.copy()
        output["picture"] = output["word"].astype(str).map(lambda w: f"/tmp/{w}.png")
        return output


class PromptDependentDummyImageLLMTransformation(DummyImageLLMTransformation):
    def __init__(self, image_started: Event, max_workers: int = 1):
        super().__init__(image_started=image_started, max_workers=max_workers)
        self.requires_master_prompt = True


def test_pipeline_runs_image_serial_when_image_workers_is_one(monkeypatch):
    image_started = Event()
    text_transform = DummyTextLLMTransformation(image_started=image_started)
    image_transform = DummyImageLLMTransformation(image_started=image_started, max_workers=1)

    monkeypatch.setattr(
        pipeline_module, "LLMTransformation", DummyTextLLMTransformation
    )
    monkeypatch.setattr(
        pipeline_module, "LLMImageTransformation", DummyImageLLMTransformation
    )

    db_client = FakeDBClient()
    events = []
    pipeline = TransformationPipeline(
        db_client=db_client,
        transformations=[text_transform, image_transform],
        table_name="test_table",
    )

    result = pipeline.transform_data_with_progress(
        words=["hola", "adios"],
        progress_callback=lambda event: events.append(event),
    )

    assert text_transform.saw_image_started is False
    assert "sentence_1" in result.columns
    assert "picture" in result.columns
    assert len(result) == 2
    assert any(
        event.get("event") == "transform_complete"
        and event.get("transform_name") == "DummyImageLLMTransformation"
        for event in events
    )


def test_pipeline_starts_image_generation_in_parallel_when_image_workers_gt_one(monkeypatch):
    image_started = Event()
    text_transform = DummyTextLLMTransformation(image_started=image_started)
    image_transform = DummyImageLLMTransformation(image_started=image_started, max_workers=2)

    monkeypatch.setattr(
        pipeline_module, "LLMTransformation", DummyTextLLMTransformation
    )
    monkeypatch.setattr(
        pipeline_module, "LLMImageTransformation", DummyImageLLMTransformation
    )

    db_client = FakeDBClient()
    pipeline = TransformationPipeline(
        db_client=db_client,
        transformations=[text_transform, image_transform],
        table_name="test_table",
    )

    _ = pipeline.transform_data(words=["hola", "adios"])
    assert text_transform.saw_image_started is True


def test_pipeline_keeps_image_dependent_when_master_prompt_is_required(monkeypatch):
    image_started = Event()
    text_transform = DummyTextLLMTransformation(image_started=image_started)
    image_transform = PromptDependentDummyImageLLMTransformation(
        image_started=image_started,
        max_workers=2,
    )

    monkeypatch.setattr(
        pipeline_module, "LLMTransformation", DummyTextLLMTransformation
    )
    monkeypatch.setattr(
        pipeline_module,
        "LLMImageTransformation",
        PromptDependentDummyImageLLMTransformation,
    )

    db_client = FakeDBClient()
    pipeline = TransformationPipeline(
        db_client=db_client,
        transformations=[text_transform, image_transform],
        table_name="test_table",
    )

    _ = pipeline.transform_data(words=["hola", "adios"])
    assert text_transform.saw_image_started is False


def test_pipeline_with_only_image_transform_still_applies(monkeypatch):
    image_started = Event()
    image_transform = DummyImageLLMTransformation(image_started=image_started)

    monkeypatch.setattr(
        pipeline_module, "LLMImageTransformation", DummyImageLLMTransformation
    )

    db_client = FakeDBClient()
    pipeline = TransformationPipeline(
        db_client=db_client,
        transformations=[image_transform],
        table_name="test_table",
    )

    result = pipeline.transform_data(words=["hola"])

    assert "picture" in result.columns
    assert result.loc[0, "picture"] == "/tmp/hola.png"
