import os
import logging
from pymongo import MongoClient
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MongoDBClient:
    def __init__(self, mongo_uri: str = None, db_name: str = 'mydatabase', collection_name: str = 'mycollection'):
        # Fetch credentials from environment variables if not provided
        mongo_uri = mongo_uri or f'mongodb://{os.getenv("MONGO_INITDB_ROOT_USERNAME")}:{os.getenv("MONGO_INITDB_ROOT_PASSWORD")}@{os.getenv("DB_HOST")}:{os.getenv("DB_PORT")}/'
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]

    def delete_duplicates(self, field_name: str = 'word') -> None:
        """Deletes duplicate records in the collection based on a specific field."""
        pipeline = [
            {"$group": {
                "_id": {field_name: f"${field_name}"},
                "count": {"$sum": 1},
                "ids": {"$push": "$_id"}
            }},
            {"$match": {"count": {"$gt": 1}}}
        ]

        try:
            duplicates = self.collection.aggregate(pipeline)
            for duplicate in duplicates:
                ids_to_delete = duplicate['ids'][1:]  # Keep the first document, delete the rest
                self.collection.delete_many({"_id": {"$in": ids_to_delete}})
            logger.info("Duplicate records deleted.")
        except Exception as e:
            logger.error(f"Error deleting duplicates: {e}")

    def find_record(self, word: str) -> Optional[Dict[str, Any]]:
        """Find a record by 'word'."""
        try:
            return self.collection.find_one({'word': word})
        except Exception as e:
            logger.error(f"Error finding record for '{word}': {e}")
            return None

    def update_field(self, record: Dict[str, Any], field_name: str, value: Any) -> None:
        """Update a specific field in a record."""
        try:
            if isinstance(record, dict):
                self.collection.update_one(
                    {'word': record['word']},
                    {'$set': {field_name: value}}
                )
                logger.info(f"Updated '{field_name}' for '{record['word']}' to '{value}'.")
            else:
                logger.error(f"Expected a dictionary or pandas Series, but got {type(record)}.")
        except Exception as e:
            logger.error(f"Error updating field '{field_name}' for '{record.get('word', 'unknown')}': {e}")


    def __insert_record_updater(self, record, update_fields, existing_record, column_name):
        """Helper method to update fields if they are missing."""
        if not existing_record.get(column_name):
            update_fields[column_name] = record.get(column_name)

    def insert_record(self, record: Dict[str, Any], columns: List[str], force: bool = False) -> None:
        """Insert or update a record."""
        try:
            existing_record = self.collection.find_one({'word': record['word']})

            if existing_record:
                update_fields = {}
                for column_name in columns:
                    self.__insert_record_updater(record, update_fields, existing_record, column_name)

                if update_fields:
                    self.collection.update_one(
                        {'word': record['word']},
                        {'$set': update_fields}
                    )
                    logger.info(f"Record for '{record['word']}' updated with {update_fields}.")
                else:
                    logger.info(f"Record for '{record['word']}' already has all fields. No update needed.")
            else:
                # If no existing record, insert the new record
                self.collection.insert_one(record)
                logger.info(f"Record for '{record['word']}' inserted.")
        except Exception as e:
            logger.error(f"Error inserting or updating record for '{record['word']}': {e}")

    def get_categories(self, word: str) -> List[str]:
        """Retrieve categories associated with a 'word'."""
        try:
            record = self.find_record(word)
            if record and 'categories' in record:
                return [i for i in record['categories'] if i is not None]
            return []
        except Exception as e:
            logger.error(f"Error getting categories for '{word}': {e}")
            return []

    def get_all_categories(self) -> List[str]:
        """Retrieve all distinct categories in the collection."""
        try:
            return [i for i in self.collection.distinct("categories") if i is not None]
        except Exception as e:
            logger.error(f"Error retrieving categories: {e}")
            return []

    def add_category(self, word: str, new_category: str) -> None:
        """Add a new category to a specific 'word'."""
        if new_category is None:
            logger.warning(f"Cannot add None as a category for '{word}'.")
            return

        try:
            query = {'word': word}
            update = {'$addToSet': {'categories': new_category}}

            result = self.collection.update_one(query, update, upsert=True)

            if result.matched_count == 0:
                logger.info(f"Created new record for '{word}' with category '{new_category}'.")
            else:
                logger.info(f"Updated record for '{word}' with category '{new_category}'.")
        except Exception as e:
            logger.error(f"Error adding category '{new_category}' to '{word}': {e}")

    def close(self) -> None:
        """Close the MongoDB connection."""
        try:
            self.client.close()
            logger.info("MongoDB connection closed.")
        except Exception as e:
            logger.error(f"Error closing MongoDB connection: {e}")
