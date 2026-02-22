"""Tests for SQLAlchemyClient persistence semantics."""

from ankineitor.pipeline.db_client import SQLAlchemyClient


def test_insert_record_backfills_empty_string_fields(tmp_path):
    db_path = tmp_path / "pipeline.db"
    client = SQLAlchemyClient(db_path=str(db_path))

    client.insert_record(
        record={"word": "hola", "translation": "", "audio": "   "},
        columns=["translation", "audio"],
        table_name="hanzi_processing",
        field_name="word",
    )

    client.insert_record(
        record={"word": "hola", "translation": "hello", "audio": "/tmp/hola.mp3"},
        columns=["translation", "audio"],
        table_name="hanzi_processing",
        field_name="word",
    )

    record = client.find_record("hola", "hanzi_processing", "word")
    assert record is not None
    assert record["translation"] == "hello"
    assert record["audio"] == "/tmp/hola.mp3"


def test_insert_record_does_not_overwrite_non_missing_fields(tmp_path):
    db_path = tmp_path / "pipeline.db"
    client = SQLAlchemyClient(db_path=str(db_path))

    client.insert_record(
        record={"word": "gracias", "translation": "thank you"},
        columns=["translation"],
        table_name="hanzi_processing",
        field_name="word",
    )

    client.insert_record(
        record={"word": "gracias", "translation": "thanks"},
        columns=["translation"],
        table_name="hanzi_processing",
        field_name="word",
    )

    record = client.find_record("gracias", "hanzi_processing", "word")
    assert record is not None
    assert record["translation"] == "thank you"


def test_insert_many_records_missing_fields_updates_in_single_batch(tmp_path):
    db_path = tmp_path / "pipeline.db"
    client = SQLAlchemyClient(db_path=str(db_path))

    client.insert_many_records(
        records=[
            {"word": "uno", "translation": "", "audio": None},
            {"word": "dos", "translation": "two", "audio": "/tmp/dos.mp3"},
        ],
        table_name="hanzi_processing",
    )

    client.insert_many_records_missing_fields(
        records=[
            {"word": "uno", "translation": "one", "audio": "/tmp/uno.mp3"},
            {"word": "dos", "translation": "TWO", "audio": "/tmp/dos_v2.mp3"},
            {"word": "tres", "translation": "three", "audio": "/tmp/tres.mp3"},
        ],
        columns=["translation", "audio"],
        table_name="hanzi_processing",
        field_name="word",
    )

    uno = client.find_record("uno", "hanzi_processing", "word")
    dos = client.find_record("dos", "hanzi_processing", "word")
    tres = client.find_record("tres", "hanzi_processing", "word")
    assert uno is not None and dos is not None and tres is not None

    # Missing fields should be filled.
    assert uno["translation"] == "one"
    assert uno["audio"] == "/tmp/uno.mp3"

    # Existing non-missing fields should not be overwritten.
    assert dos["translation"] == "two"
    assert dos["audio"] == "/tmp/dos.mp3"

    # New rows should still be inserted.
    assert tres["translation"] == "three"
    assert tres["audio"] == "/tmp/tres.mp3"
