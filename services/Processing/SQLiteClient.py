import os
import sqlite3
import json
from loguru import logger
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

load_dotenv()


class SQLiteClient:
    def __init__(self, db_path: str = "ankineitor.db"):
        """
        Initializes a client for a SQLite database.

        Args:
            db_path (str): The file path for the SQLite database.
        """
        try:
            self.db_path = db_path
            # connect() will create the file if it doesn't exist
            self.conn = sqlite3.connect(db_path)
            # Use Row factory to access columns by name (like a dict)
            self.conn.row_factory = sqlite3.Row
            self.cur = self.conn.cursor()
            self._create_tables()
            logger.info(f"Connected to SQLite database at '{db_path}'.")
        except sqlite3.Error as e:
            logger.critical(f"Error connecting to SQLite database: {e}")
            raise

    def _create_tables(self) -> None:
        """
        Ensures that the required tables exist in the database.
        """
        try:
            # Table for the LLM inference results
            self.cur.execute(
                """
            CREATE TABLE IF NOT EXISTS llm_inference (
                word TEXT PRIMARY KEY,
                example_sentences TEXT,
                improved_meaning TEXT,
                sentence_1 TEXT,
                sentence_2 TEXT,
                sentence_3 TEXT,
                meaning_english TEXT,
                meaning_spanish TEXT
            );
            """
            )

            # Table for Hanzi processing and categorization
            self.cur.execute(
                """
            CREATE TABLE IF NOT EXISTS hanzi_processing (
                word TEXT PRIMARY KEY,
                categories TEXT  -- Stored as a JSON array string
            );
            """
            )
            self.conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Error creating tables: {e}")
            self.conn.rollback()

    # --- General Func ---

    def delete_duplicates(self, table_name: str, field_name: str) -> None:
        """Deletes duplicate records in the table based on a specific field."""
        # This query keeps the record with the minimum rowid and deletes others
        sql = f"""
        DELETE FROM {table_name}
        WHERE rowid NOT IN (
            SELECT MIN(rowid)
            FROM {table_name}
            GROUP BY {field_name}
        );
        """
        try:
            self.cur.execute(sql)
            self.conn.commit()
            logger.info(
                f"Duplicate records deleted from '{table_name}' based on '{field_name}'."
            )
        except sqlite3.Error as e:
            logger.error(f"Error deleting duplicates: {e}")
            self.conn.rollback()

    def find_record(
        self, key: str, table_name: str, field_name: str
    ) -> Optional[Dict[str, Any]]:
        """Find a record by a key in a specific field."""
        sql = f"SELECT * FROM {table_name} WHERE {field_name} = ?"
        try:
            self.cur.execute(sql, (key,))
            row = self.cur.fetchone()
            # Convert sqlite3.Row to a standard dict for compatibility
            return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error(f"Error finding record for '{key}': {e}")
            return None

    def update_field(
        self,
        table_name: str,
        key_field: str,
        key_value: Any,
        column_to_update: str,
        new_value: Any,
    ) -> None:
        """
        Update a specific field in a record found by a key.
        NOTE: This signature is clearer and more functional than the original.
        """
        sql = f"UPDATE {table_name} SET {column_to_update} = ? WHERE {key_field} = ?"
        try:
            self.cur.execute(sql, (new_value, key_value))
            self.conn.commit()
            logger.info(
                f"Updated '{column_to_update}' for '{key_value}' to '{new_value}'."
            )
        except sqlite3.Error as e:
            logger.error(
                f"Error updating field '{column_to_update}' for '{key_value}': {e}"
            )
            self.conn.rollback()

    def insert_record(
        self,
        record: Dict[str, Any],
        columns: List[str],
        table_name: str,
        field_name: str,
    ) -> None:
        """
        Insert or update a record.
        If the record exists, it only updates fields that are missing or null.
        """
        try:
            key_value = record[field_name]
            existing_record = self.find_record(key_value, table_name, field_name)

            if existing_record:
                # Update logic: Only fill in missing fields
                update_fields = {}
                for col in columns:
                    # Check if key is missing, or if value is None
                    if (existing_record.get(col) is None) and (
                        record.get(col) is not None
                    ):
                        update_fields[col] = record.get(col)

                if update_fields:
                    set_clause = ", ".join(
                        [f"{col} = ?" for col in update_fields.keys()]
                    )
                    values = list(update_fields.values())
                    sql = f"UPDATE {table_name} SET {set_clause} WHERE {field_name} = ?"

                    self.cur.execute(sql, (*values, key_value))
                    self.conn.commit()
                    logger.info(
                        f"Record for '{key_value}' updated with {list(update_fields.keys())}."
                    )
                else:
                    logger.info(
                        f"Record for '{key_value}' already has all fields. No update needed."
                    )

            else:
                # Insert logic: Insert the new record
                # Filter record to only include keys that exist as columns
                self.cur.execute(f"PRAGMA table_info({table_name})")
                table_columns = {row["name"] for row in self.cur.fetchall()}

                filtered_record = {
                    k: v for k, v in record.items() if k in table_columns
                }

                cols = ", ".join(filtered_record.keys())
                placeholders = ", ".join(["?" for _ in filtered_record])
                values = tuple(filtered_record.values())

                sql = f"INSERT INTO {table_name} ({cols}) VALUES ({placeholders})"
                self.cur.execute(sql, values)
                self.conn.commit()
                logger.info(f"Record for '{key_value}' inserted.")

        except (sqlite3.Error, KeyError) as e:
            logger.error(
                f"Error inserting or updating record for '{record.get(field_name)}': {e}"
            )
            self.conn.rollback()

    # --- Specific for categories ---

    def get_categories_by_word(
        self, key: str, table_name: str = "hanzi_processing"
    ) -> List[str]:
        """Retrieve categories (from JSON) associated with a 'word'."""
        try:
            record = self.find_record(key, table_name, "word")
            if record and record.get("categories"):
                # Load categories from the JSON string
                return json.loads(record["categories"])
            return []
        except (sqlite3.Error, json.JSONDecodeError) as e:
            logger.error(f"Error getting categories for '{key}': {e}")
            return []

    def get_all_categories(self, table_name: str = "hanzi_processing") -> List[str]:
        """Retrieve all distinct categories from all records."""
        all_categories = set()
        sql = f"SELECT categories FROM {table_name} WHERE categories IS NOT NULL"
        try:
            self.cur.execute(sql)
            for row in self.cur.fetchall():
                try:
                    categories_list = json.loads(row["categories"])
                    all_categories.update(categories_list)
                except (json.JSONDecodeError, TypeError):
                    continue  # Skip malformed JSON
            return [cat for cat in all_categories if cat is not None]
        except sqlite3.Error as e:
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

        try:
            existing_record = self.find_record(key, table_name, field_name)

            if existing_record:
                # Record exists, update its category list
                try:
                    cats_list = json.loads(existing_record.get("categories") or "[]")
                except json.JSONDecodeError:
                    cats_list = []

                if new_category not in cats_list:
                    cats_list.append(new_category)
                    new_cats_str = json.dumps(cats_list)

                    sql = (
                        f"UPDATE {table_name} SET categories = ? WHERE {field_name} = ?"
                    )
                    self.cur.execute(sql, (new_cats_str, key))
                    self.conn.commit()
                    logger.info(
                        f"Updated record for '{key}' with category '{new_category}'."
                    )
                else:
                    logger.info(
                        f"Category '{new_category}' already exists for '{key}'."
                    )

            else:
                # Record doesn't exist, create it (upsert=True)
                new_cats_str = json.dumps([new_category])
                sql = (
                    f"INSERT INTO {table_name} ({field_name}, categories) VALUES (?, ?)"
                )
                self.cur.execute(sql, (key, new_cats_str))
                self.conn.commit()
                logger.info(
                    f"Created new record for '{key}' with category '{new_category}'."
                )

        except sqlite3.Error as e:
            logger.error(f"Error adding category '{new_category}' to '{key}': {e}")
            self.conn.rollback()

    def close(self) -> None:
        """Close the SQLite connection."""
        try:
            self.conn.close()
            logger.info("SQLite connection closed.")
        except sqlite3.Error as e:
            logger.error(f"Error closing SQLite connection: {e}")
