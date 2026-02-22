import os
import json
import re
from loguru import logger
from typing import Optional, Dict, Any, List, Type, Generator
from contextlib import contextmanager

# SQLAlchemy Imports
from sqlalchemy import create_engine, Column, String, Text, select, func, delete, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

# Load environment variables
from dotenv import load_dotenv

load_dotenv()

# --- 1. Define Database Models (Schema) ---


class Base(DeclarativeBase):
    """Base class for all declarative models."""

    pass


class LlmInference(Base):
    """Maps to the 'llm_inference' table."""

    __tablename__ = "llm_inference"

    word = Column(String, primary_key=True)
    example_sentences = Column(Text)
    improved_meaning = Column(Text)
    sentence_1 = Column(Text)
    sentence_2 = Column(Text)
    sentence_3 = Column(Text)
    meaning_english = Column(Text)
    meaning_spanish = Column(Text)
    profile_id = Column(String)
    profile_version = Column(String)
    word_model = Column(String)
    pinyin = Column(Text)
    part_of_speech = Column(Text)
    character_breakdown = Column(Text)
    detailed_explanation_english = Column(Text)
    detailed_explanation_spanish = Column(Text)
    word_with_stress = Column(Text)
    romanization = Column(Text)
    aspect_pair = Column(Text)
    register = Column(Text)
    grammar_formula = Column(Text)
    mnemonic_hook_spanish = Column(Text)
    piter_summer_variant = Column(Text)
    edge_case_notes = Column(Text)
    synonyms_json = Column(Text)
    antonyms_json = Column(Text)
    collocations_json = Column(Text)
    sentences_json = Column(Text)
    synonyms_rendered = Column(Text)
    antonyms_rendered = Column(Text)
    collocations_rendered = Column(Text)
    sentences_rendered_html = Column(Text)


class LlmRawResponse(Base):
    """Maps to the 'llm_raw_response' table."""

    __tablename__ = "llm_raw_response"

    record_id = Column(String, primary_key=True)
    created_at = Column(String)
    cache_key_word = Column(String)
    word = Column(String)
    profile_id = Column(String)
    profile_version = Column(String)
    model_name = Column(String)
    parse_status = Column(String)
    parse_error = Column(Text)
    raw_response_text = Column(Text)
    extracted_payload_json = Column(Text)
    normalized_payload_json = Column(Text)


class ImagePromptInference(Base):
    """Maps to the 'image_prompt_inference' table."""

    __tablename__ = "image_prompt_inference"

    word = Column(String, primary_key=True)
    source_word = Column(String)
    image_term_type = Column(String)
    visual_description = Column(Text)
    master_image_prompt = Column(Text)
    image_generation_skip_reason = Column(Text)


class HanziProcessing(Base):
    """Maps to the 'hanzi_processing' table."""

    __tablename__ = "hanzi_processing"

    word = Column(String, primary_key=True)
    categories = Column(Text, default="[]")  # Store as a JSON string
    pinyin = Column(String)
    translation = Column(Text)
    audio = Column(String)
    timestamp = Column(String)
    # Add other columns from your transformations here if needed


# --- 2. SQLAlchemy Client ---


class SQLAlchemyClient:
    def __init__(self, db_path: str = "ankineitor.db"):
        """
        Initializes a client for a SQLite database using SQLAlchemy.

        Args:
            db_path (str): The file path for the SQLite database. (e.g., 'sqlite:///ankineitor.db')
        """
        if not db_path.startswith("sqlite://"):
            db_path = f"sqlite:///{db_path}"

        try:
            self.engine = create_engine(db_path)
            # SessionLocal is a factory for creating new Session objects
            self.SessionLocal = sessionmaker(
                autocommit=False, autoflush=False, bind=self.engine
            )

            # Create tables if they don't exist
            Base.metadata.create_all(self.engine)
            self._run_schema_migrations()

            # Map table names (from processor) to their Model classes
            self._model_map: Dict[str, Type[Base]] = {
                "llm_inference": LlmInference,
                "llm_raw_response": LlmRawResponse,
                "image_prompt_inference": ImagePromptInference,
                "hanzi_processing": HanziProcessing,
            }
            logger.info(f"Connected to SQLAlchemy database at '{db_path}'.")
        except SQLAlchemyError as e:
            logger.critical(f"Error connecting to SQLAlchemy database: {e}")
            raise

    def _run_schema_migrations(self) -> None:
        """Apply lightweight additive migrations for SQLite tables."""
        if self.engine.url.get_backend_name() != "sqlite":
            return

        self._ensure_sqlite_columns(
            table_name="llm_inference",
            columns={
                "profile_id": "TEXT",
                "profile_version": "TEXT",
                "word_model": "TEXT",
                "pinyin": "TEXT",
                "part_of_speech": "TEXT",
                "character_breakdown": "TEXT",
                "detailed_explanation_english": "TEXT",
                "detailed_explanation_spanish": "TEXT",
                "word_with_stress": "TEXT",
                "romanization": "TEXT",
                "aspect_pair": "TEXT",
                "register": "TEXT",
                "grammar_formula": "TEXT",
                "mnemonic_hook_spanish": "TEXT",
                "piter_summer_variant": "TEXT",
                "edge_case_notes": "TEXT",
                "synonyms_json": "TEXT",
                "antonyms_json": "TEXT",
                "collocations_json": "TEXT",
                "sentences_json": "TEXT",
                "synonyms_rendered": "TEXT",
                "antonyms_rendered": "TEXT",
                "collocations_rendered": "TEXT",
                "sentences_rendered_html": "TEXT",
            },
        )
        self._ensure_sqlite_columns(
            table_name="llm_raw_response",
            columns={
                "created_at": "TEXT",
                "cache_key_word": "TEXT",
                "word": "TEXT",
                "profile_id": "TEXT",
                "profile_version": "TEXT",
                "model_name": "TEXT",
                "parse_status": "TEXT",
                "parse_error": "TEXT",
                "raw_response_text": "TEXT",
                "extracted_payload_json": "TEXT",
                "normalized_payload_json": "TEXT",
            },
        )

    def _ensure_sqlite_columns(self, table_name: str, columns: Dict[str, str]) -> None:
        """Add missing columns to SQLite tables using ALTER TABLE ADD COLUMN."""
        identifier_pattern = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
        if not identifier_pattern.match(table_name):
            raise ValueError(f"Unsafe table name for migration: {table_name}")

        with self.engine.begin() as conn:
            existing = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
            existing_names = {row[1] for row in existing}

            for col_name, col_type in columns.items():
                if not identifier_pattern.match(col_name):
                    raise ValueError(f"Unsafe column name for migration: {col_name}")
                if col_name in existing_names:
                    continue
                conn.execute(
                    text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}")
                )
                logger.info(
                    f"Schema migration: added column '{col_name}' to '{table_name}'."
                )

    @contextmanager
    def _get_session(self) -> Generator[Session, None, None]:
        """
        Provides a transactional session.
        This is the best practice for session management.
        """
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except SQLAlchemyError as e:
            logger.error(f"Database error occurred: {e}. Rolling back.")
            session.rollback()
            raise
        finally:
            session.close()

    def _get_model(self, table_name: str) -> Type[Base]:
        """Helper to get the model class from its string name."""
        model = self._model_map.get(table_name)
        if not model:
            raise ValueError(f"No model found for table name: {table_name}")
        return model

    @staticmethod
    def _is_missing_value(value: Any) -> bool:
        """Treat null-like/blank values as missing for backfill updates."""
        if value is None:
            return True
        if isinstance(value, str) and not value.strip():
            return True
        # NaN check without pandas dependency.
        try:
            return bool(value != value)
        except Exception:
            return False

    # --- General Func ---

    def find_record(
        self, key: str, table_name: str, field_name: str
    ) -> Optional[Dict[str, Any]]:
        """Find a single record by a key in a specific field."""
        try:
            model = self._get_model(table_name)
            with self._get_session() as session:
                # Use getattr to filter on a dynamic field name
                instance = (
                    session.query(model)
                    .filter(getattr(model, field_name) == key)
                    .first()
                )

                if instance:
                    # Convert the ORM object to a dict for compatibility
                    return {
                        c.name: getattr(instance, c.name)
                        for c in instance.__table__.columns
                    }
                return None
        except (SQLAlchemyError, ValueError) as e:
            logger.error(f"Error finding record for '{key}': {e}")
            return None

    # --- NEW BULK METHOD (for pipeline) ---
    def find_many_by_field(
        self, keys: List[Any], table_name: str, field_name: str
    ) -> List[Dict[str, Any]]:
        """
        Finds all records where 'field_name' is in the list of 'keys'.
        """
        if len(keys) == 0:
            return []

        try:
            model = self._get_model(table_name)
            key_column = getattr(model, field_name)

            with self._get_session() as session:
                # Use .in_() for a bulk SELECT ... WHERE field IN (...) query
                instances = session.query(model).filter(key_column.in_(keys)).all()

                # Convert list of ORM objects to a list of dicts
                return [
                    {c.name: getattr(inst, c.name) for c in inst.__table__.columns}
                    for inst in instances
                ]
        except (SQLAlchemyError, ValueError) as e:
            logger.error(f"Error finding many records by {field_name}: {e}")
            return []

    def insert_record(
        self,
        record: Dict[str, Any],
        columns: List[str],
        table_name: str,
        field_name: str,
    ) -> None:
        """
        Insert or update a single record.
        If the record exists, it only updates fields that are missing or null.
        """
        try:
            model = self._get_model(table_name)
            key_value = record[field_name]

            with self._get_session() as session:
                existing = (
                    session.query(model)
                    .filter(getattr(model, field_name) == key_value)
                    .first()
                )

                if existing:
                    update_made = False
                    for col in columns:
                        if col not in record:
                            continue
                        previous_value = getattr(existing, col)
                        incoming_value = record[col]
                        if self._is_missing_value(
                            previous_value
                        ) and not self._is_missing_value(
                            incoming_value
                        ):
                            setattr(existing, col, incoming_value)
                            update_made = True

                    if update_made:
                        session.merge(existing)  # Merge changes
                        logger.info(
                            f"Record for '{key_value}' updated with missing fields."
                        )
                    else:
                        logger.info(
                            f"Record for '{key_value}' already has all fields. No update needed."
                        )

                else:
                    valid_data = {
                        c.name: record.get(c.name)
                        for c in model.__table__.columns
                        if c.name in record
                    }
                    new_instance = model(**valid_data)
                    session.add(new_instance)
                    logger.info(f"Record for '{key_value}' inserted.")

        except (SQLAlchemyError, ValueError, KeyError) as e:
            logger.error(
                f"Error inserting or updating record for '{record.get(field_name)}': {e}"
            )

    # --- NEW BULK METHOD (for pipeline) ---
    def insert_many_records(
        self, records: List[Dict[str, Any]], table_name: str
    ) -> None:
        """
        Inserts multiple records into the database in a single transaction.
        Assumes records are new and does not check for duplicates.
        """
        if not records:
            return

        try:
            model = self._get_model(table_name)
            with self._get_session() as session:
                # session.bulk_insert_mappings is highly efficient
                session.bulk_insert_mappings(model, records)
                logger.info(
                    f"Bulk inserted {len(records)} records into '{table_name}'."
                )
        except (SQLAlchemyError, ValueError) as e:
            logger.error(f"Error bulk inserting records: {e}")

    def insert_many_records_missing_fields(
        self,
        records: List[Dict[str, Any]],
        columns: List[str],
        table_name: str,
        field_name: str,
    ) -> None:
        """
        Insert or update many records in one transaction.
        Existing rows only receive values for currently missing fields.
        """
        if not records:
            return

        try:
            model = self._get_model(table_name)
            key_column = getattr(model, field_name)

            normalized_records: List[Dict[str, Any]] = []
            seen_keys = set()
            for record in records:
                if field_name not in record:
                    continue
                key_value = record[field_name]
                if key_value in seen_keys:
                    continue
                normalized_records.append(record)
                seen_keys.add(key_value)

            if not normalized_records:
                return

            key_values = [record[field_name] for record in normalized_records]
            inserted_count = 0
            updated_count = 0

            with self._get_session() as session:
                existing_instances = session.query(model).filter(
                    key_column.in_(key_values)
                ).all()
                existing_by_key = {
                    getattr(instance, field_name): instance
                    for instance in existing_instances
                }

                for record in normalized_records:
                    key_value = record[field_name]
                    existing = existing_by_key.get(key_value)

                    if existing is None:
                        valid_data = {
                            c.name: record.get(c.name)
                            for c in model.__table__.columns
                            if c.name in record
                        }
                        session.add(model(**valid_data))
                        inserted_count += 1
                        continue

                    update_made = False
                    for col in columns:
                        if col not in record:
                            continue
                        previous_value = getattr(existing, col)
                        incoming_value = record[col]
                        if self._is_missing_value(
                            previous_value
                        ) and not self._is_missing_value(incoming_value):
                            setattr(existing, col, incoming_value)
                            update_made = True

                    if update_made:
                        session.merge(existing)
                        updated_count += 1

            logger.info(
                "Bulk upserted {} record(s) in '{}' (inserted={}, updated={}).".format(
                    len(normalized_records),
                    table_name,
                    inserted_count,
                    updated_count,
                )
            )
        except (SQLAlchemyError, ValueError) as e:
            logger.error(f"Error bulk upserting records with missing-fields policy: {e}")

    def update_field(
        self,
        table_name: str,
        key_field: str,
        key_value: Any,
        column_to_update: str,
        new_value: Any,
    ) -> None:
        """Update a specific field in a record found by a key."""
        try:
            model = self._get_model(table_name)
            with self._get_session() as session:
                session.query(model).filter(
                    getattr(model, key_field) == key_value
                ).update({column_to_update: new_value})
                logger.info(
                    f"Updated '{column_to_update}' for '{key_value}' to '{new_value}'."
                )
        except (SQLAlchemyError, ValueError) as e:
            logger.error(
                f"Error updating field '{column_to_update}' for '{key_value}': {e}"
            )

    def delete_duplicates(self, table_name: str, field_name: str) -> None:
        """Deletes duplicate records in the table based on a specific field."""
        try:
            model = self._get_model(table_name)
            pk_col = getattr(model, model.__mapper__.primary_key[0].name)

            subq = (
                select(func.min(pk_col))
                .group_by(getattr(model, field_name))
                .scalar_subquery()
            )

            stmt = delete(model).where(pk_col.notin_(subq))

            with self._get_session() as session:
                result = session.execute(stmt)
                logger.info(
                    f"Duplicate records deleted from '{table_name}': {result.rowcount} rows affected."
                )

        except (SQLAlchemyError, ValueError) as e:
            logger.error(f"Error deleting duplicates: {e}")

    # --- Specific for categories ---

    def get_categories_by_word(
        self, key: str, table_name: str = "hanzi_processing"
    ) -> List[str]:
        """Retrieve categories (from JSON) associated with a 'word'."""
        try:
            record = self.find_record(key, table_name, "word")
            if record and record.get("categories"):
                return json.loads(record["categories"])
            return []
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Error getting categories for '{key}': {e}")
            return []

    def get_all_categories(self, table_name: str = "hanzi_processing") -> List[str]:
        """Retrieve all distinct categories from all records."""
        all_categories = set()
        model = self._get_model(table_name)
        try:
            with self._get_session() as session:
                results = (
                    session.query(model.categories)
                    .filter(model.categories.isnot(None))
                    .all()
                )
                for (cat_json,) in results:
                    try:
                        all_categories.update(json.loads(cat_json))
                    except (json.JSONDecodeError, TypeError):
                        continue
            return [cat for cat in all_categories if cat is not None]
        except (SQLAlchemyError, ValueError) as e:
            logger.error(f"Error retrieving categories: {e}")
            return []

    def add_category(
        self,
        key: str,
        new_category: str,
        table_name: str = "hanzi_processing",
        field_name: str = "word",
    ) -> None:
        """Add a new category to a 'word', updating the JSON list."""
        if new_category is None:
            logger.warning(f"Cannot add None as a category for '{key}'.")
            return

        model = self._get_model(table_name)
        try:
            with self._get_session() as session:
                instance = (
                    session.query(model)
                    .filter(getattr(model, field_name) == key)
                    .first()
                )

                if instance:
                    try:
                        cats_list = json.loads(instance.categories or "[]")
                    except json.JSONDecodeError:
                        cats_list = []

                    if new_category not in cats_list:
                        cats_list.append(new_category)
                        instance.categories = json.dumps(cats_list)
                        session.merge(instance)
                        logger.info(
                            f"Updated record for '{key}' with category '{new_category}'."
                        )
                    else:
                        logger.info(
                            f"Category '{new_category}' already exists for '{key}'."
                        )

                else:
                    new_cats_str = json.dumps([new_category])
                    new_instance = model(
                        **{field_name: key, "categories": new_cats_str}
                    )
                    session.add(new_instance)
                    logger.info(
                        f"Created new record for '{key}' with category '{new_category}'."
                    )

        except (SQLAlchemyError, ValueError) as e:
            logger.error(f"Error adding category '{new_category}' to '{key}': {e}")

    # --- Connection Func ---

    def close(self) -> None:
        """Dispose of the engine's connection pool."""
        try:
            self.engine.dispose()
            logger.info("SQLAlchemy engine connection pool disposed.")
        except SQLAlchemyError as e:
            logger.error(f"Error disposing SQLAlchemy engine: {e}")
