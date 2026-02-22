"""Tests for cache backfill behavior in TransformationPipeline."""

from dataclasses import dataclass
from typing import Any, Dict, List

import pandas as pd

from ankineitor.pipeline.pipeline import TransformationPipeline
from ankineitor.pipeline.transformations import Transformation


@dataclass
class _FakeDBClient:
    rows: Dict[str, Dict[str, Any]]

    def __init__(self, initial_rows: List[Dict[str, Any]]):
        self.rows = {str(row["word"]): dict(row) for row in initial_rows}
        self.bulk_inserts: List[Dict[str, Any]] = []
        self.backfill_updates: List[Dict[str, Any]] = []
        self.bulk_backfill_calls = 0

    @staticmethod
    def _is_missing_value(value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str) and not value.strip():
            return True
        return False

    def find_many_by_field(self, keys, table_name, field_name):
        del table_name, field_name
        return [dict(self.rows[str(key)]) for key in keys if str(key) in self.rows]

    def insert_many_records(self, records, table_name):
        del table_name
        for record in records:
            stored = dict(record)
            self.rows[str(stored["word"])] = stored
            self.bulk_inserts.append(stored)

    def insert_record(self, record, columns, table_name, field_name):
        del table_name, field_name
        key = str(record["word"])
        existing = self.rows.get(key, {"word": key})
        for column in columns:
            if (
                column in record
                and self._is_missing_value(existing.get(column))
                and not self._is_missing_value(record[column])
            ):
                existing[column] = record[column]
        self.rows[key] = existing
        self.backfill_updates.append(dict(existing))

    def insert_many_records_missing_fields(
        self, records, columns, table_name, field_name
    ):
        del table_name, field_name
        self.bulk_backfill_calls += 1
        for record in records:
            self.insert_record(
                record=record,
                columns=columns,
                table_name="hanzi_processing",
                field_name="word",
            )


class _DummyTimestampTransform(Transformation):
    def __init__(self):
        self.call_count = 0

    @property
    def column_name(self) -> str:
        return "timestamp"

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        self.call_count += 1
        out = df.copy()
        out["timestamp"] = "NEW_TIMESTAMP"
        return out


class _DummyAudioTransform(Transformation):
    def __init__(self):
        self.call_count = 0

    @property
    def column_name(self) -> str:
        return "audio"

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        self.call_count += 1
        out = df.copy()
        out["audio"] = out["word"].astype(str).map(lambda word: f"/tmp/{word}.mp3")
        return out


def test_pipeline_backfills_missing_main_transform_outputs_for_cached_words():
    db_client = _FakeDBClient(
        initial_rows=[{"word": "hola", "timestamp": "OLD_TIMESTAMP", "audio": None}]
    )
    timestamp = _DummyTimestampTransform()
    audio = _DummyAudioTransform()
    pipeline = TransformationPipeline(
        db_client=db_client,
        transformations=[timestamp, audio],
        table_name="hanzi_processing",
    )

    result = pipeline.transform_data(words=["hola"])

    assert timestamp.call_count == 1
    assert audio.call_count == 1
    assert result.loc[0, "word"] == "hola"
    assert result.loc[0, "audio"] == "/tmp/hola.mp3"
    # Existing non-missing values should be preserved during backfill.
    assert result.loc[0, "timestamp"] == "OLD_TIMESTAMP"
    # Backfill should update missing DB fields.
    assert db_client.rows["hola"]["audio"] == "/tmp/hola.mp3"
    assert db_client.rows["hola"]["timestamp"] == "OLD_TIMESTAMP"
    assert db_client.bulk_backfill_calls == 1


def test_pipeline_skips_main_reprocessing_when_cached_rows_are_complete():
    db_client = _FakeDBClient(
        initial_rows=[
            {"word": "hola", "timestamp": "OLD_TIMESTAMP", "audio": "/tmp/hola.mp3"}
        ]
    )
    timestamp = _DummyTimestampTransform()
    audio = _DummyAudioTransform()
    pipeline = TransformationPipeline(
        db_client=db_client,
        transformations=[timestamp, audio],
        table_name="hanzi_processing",
    )

    result = pipeline.transform_data(words=["hola"])

    assert timestamp.call_count == 0
    assert audio.call_count == 0
    assert result.loc[0, "word"] == "hola"
    assert result.loc[0, "audio"] == "/tmp/hola.mp3"
    assert result.loc[0, "timestamp"] == "OLD_TIMESTAMP"


def test_pipeline_preserves_duplicate_input_rows_in_output():
    db_client = _FakeDBClient(
        initial_rows=[
            {"word": "hola", "timestamp": "OLD_TIMESTAMP", "audio": "/tmp/hola.mp3"}
        ]
    )
    pipeline = TransformationPipeline(
        db_client=db_client,
        transformations=[],
        table_name="hanzi_processing",
    )

    result = pipeline.transform_data(words=["hola", "hola", "adios", "hola"])

    assert result["word"].tolist() == ["hola", "hola", "adios", "hola"]
    assert len(result) == 4


def test_pipeline_backfills_when_cached_value_is_blank_string():
    db_client = _FakeDBClient(
        initial_rows=[{"word": "hola", "timestamp": "OLD_TIMESTAMP", "audio": "   "}]
    )
    audio = _DummyAudioTransform()
    pipeline = TransformationPipeline(
        db_client=db_client,
        transformations=[audio],
        table_name="hanzi_processing",
    )

    result = pipeline.transform_data(words=["hola"])

    assert audio.call_count == 1
    assert result.loc[0, "audio"] == "/tmp/hola.mp3"
    assert db_client.rows["hola"]["audio"] == "/tmp/hola.mp3"
