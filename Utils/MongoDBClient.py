import os
from loguru import logger
from pymongo import MongoClient
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

load_dotenv()

class MongoDBClient:
    def __init__(self, mongo_uri: str = None, db_name: str = 'ankineitor'):
        # Fetch credentials from environment variables if not provided
        mongo_uri = mongo_uri or f'mongodb://{os.getenv("MONGO_INITDB_ROOT_USERNAME")}:{os.getenv("MONGO_INITDB_ROOT_PASSWORD")}@{os.getenv("DB_HOST")}:{os.getenv("DB_PORT")}/'
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]

    # General Func

    def delete_duplicates(self, collection_name: str, field_name: str) -> None:
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
            duplicates = self.db[collection_name].aggregate(pipeline)
            for duplicate in duplicates:
                ids_to_delete = duplicate['ids'][1:]  # Keep the first document, delete the rest
                self.db[collection_name].delete_many({"_id": {"$in": ids_to_delete}})
            logger.info("Duplicate records deleted.")
        except Exception as e:
            logger.error(f"Error deleting duplicates: {e}")

    def find_record(self, key: str, collection_name: str, field_name: str) -> Optional[Dict[str, Any]]:
        """Find a record by 'index'."""
        try:
            return self.db[collection_name].find_one({field_name: key})
        except Exception as e:
            logger.error(f"Error finding record for '{key}': {e}")
            return None

    def update_field(self, record: Dict[str, Any], value: Any, collection_name: str, field_name: str) -> None:
        """Update a specific field in a record."""
        try:
            self.db[collection_name].update_one(
                {field_name: record[field_name]},
                {'$set': {field_name: value}}
            )
            logger.info(f"Updated '{field_name}' for '{record[field_name]}' to '{value}'.")
        except Exception as e:
            logger.error(f"Error updating field '{field_name}' for '{record[field_name]}': {e}")

    def __insert_record_updater(self, record, update_fields, existing_record, column_name):
        """Helper method to update fields if they are missing."""
        if not existing_record.get(column_name):
            update_fields[column_name] = record.get(column_name)

    def insert_record(self, record: Dict[str, Any], columns: List[str],
                      collection_name: str, field_name: str, force: bool = False) -> None:
        """Insert or update a record."""
        try:
            existing_record = self.db[collection_name].find_one({field_name: record[field_name]})

            if existing_record:
                update_fields = {}
                for column_name in columns:
                    self.__insert_record_updater(record, update_fields, existing_record, column_name)

                if update_fields:
                    self.db[collection_name].update_one(
                        {field_name: record[field_name]},
                        {'$set': update_fields}
                    )
                    logger.info(f"Record for '{record[field_name]}' updated with {update_fields}.")
                else:
                    logger.info(f"Record for '{record[field_name]}' already has all fields. No update needed.")
            else:
                # If no existing record, insert the new record
                self.db[collection_name].insert_one(record)
                logger.info(f"Record for '{record[field_name]}' inserted.")
        except Exception as e:
            logger.error(f"Error inserting or updating record for '{record[field_name]}': {e}")

    # Specific for categories

    def get_categories_by_word(self, key: str, collection_name: str = 'word') -> List[str]:
        """Retrieve categories associated with a 'word'."""
        try:
            record = self.find_record(key, collection_name)
            if record and 'categories' in record:
                return [i for i in record['categories'] if i is not None]
            return []
        except Exception as e:
            logger.error(f"Error getting categories for '{key}': {e}")
            return []

    def get_all_categories(self, collection_name: str = 'word') -> List[str]:
        """Retrieve all distinct categories in the collection."""
        try:
            return [i for i in self.db[collection_name].distinct("categories") if i is not None]
        except Exception as e:
            logger.error(f"Error retrieving categories: {e}")
            return []

    def add_category(self, key: str, new_category: str, collection_name: str = 'word', field_name: str = 'word') -> None:
        """Add a new category to a specific 'word'."""
        if new_category is None:
            logger.warning(f"Cannot add None as a category for '{key}'.")
            return

        try:
            query = {field_name: key}
            update = {'$addToSet': {'categories': new_category}}

            result = self.db[collection_name].update_one(query, update, upsert=True)

            if result.matched_count == 0:
                logger.info(f"Created new record for '{key}' with category '{new_category}'.")
            else:
                logger.info(f"Updated record for '{key}' with category '{new_category}'.")
        except Exception as e:
            logger.error(f"Error adding category '{new_category}' to '{key}': {e}")

    def close(self) -> None:
        """Close the MongoDB connection."""
        try:
            self.client.close()
            logger.info("MongoDB connection closed.")
        except Exception as e:
            logger.error(f"Error closing MongoDB connection: {e}")
