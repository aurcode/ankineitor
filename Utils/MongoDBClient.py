from pymongo import MongoClient
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv
import os

load_dotenv()
debug = os.getenv('DEBUG')

class MongoDBClient:
    # mongodb://your_username:your_password@localhost:27017/', authSource='admin')
    def __init__(self, mongo_uri: str = f'mongodb://{os.getenv('MONGO_INITDB_ROOT_USERNAME')}:{os.getenv('MONGO_INITDB_ROOT_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/', db_name: str = 'mydatabase', collection_name: str = 'mycollection'):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]

    def delete_duplicates(self, field_name='hanzi'):
        # Aggregation pipeline to group by the `hanzi` field
        pipeline = [
            {
                "$group": {
                    "_id": { field_name: f"${field_name}" },  # Group by hanzi field
                    "count": { "$sum": 1 },
                    "ids": { "$push": "$_id" }  # Collect all _ids for the grouped hanzi
                }
            },
            {
                "$match": {
                    "count": { "$gt": 1 }  # Only return groups with duplicates
                }
            }
        ]

        # Run the aggregation pipeline
        duplicates = self.collection.aggregate(pipeline)

        # Iterate over the duplicates and delete all but one
        for duplicate in duplicates:
            ids_to_delete = duplicate['ids'][1:]  # Keep the first document, delete the rest
            self.collection.delete_many({ "_id": { "$in": ids_to_delete } })

        print("Duplicate records deleted")

    def find_record(self, hanzi: str) -> Optional[Dict[str, Any]]:
        """Find a record in the MongoDB collection by 'hanzi'."""
        return self.collection.find_one({'hanzi': hanzi})

    def __insert_record_updater(self, record, update_fields, existing_record, column_name):
        if not existing_record.get(column_name):
            update_fields[column_name] = record.get(column_name)

    def insert_record(self, record: Dict[str, Any], columns, force: bool = False) -> None:
        """Insert or update a record in the MongoDB collection."""
        # Buscar si existe un registro con el mismo 'hanzi'
        existing_record = self.collection.find_one({'hanzi': record['hanzi']})

        if existing_record:
            update_fields = {}

            [self.__insert_record_updater(record, update_fields, existing_record, column_name) for column_name in columns]

            if update_fields:
                self.collection.update_one(
                    {'hanzi': record['hanzi']},
                    {'$set': update_fields}
                )
                print(f"Record for '{record['hanzi']}' updated with {update_fields}.")
            else:
                print(f"Record for '{record['hanzi']}' already has 'pinyin' and 'translation'. No update needed.")
        else:
            # Si no existe el registro, lo insertamos
            self.collection.insert_one(record)
            print(f"Record for '{record['hanzi']}' inserted.")


    def get_categories(self, hanzi: str) -> List[str]:
        """Get the categories a word belongs to."""
        record = self.find_record(hanzi)
        if record and 'categories' in record:
            return [i for i in record['categories'] if i is not None ]
        return []

    def get_all_categories(self) -> list:
        """Retrieve all distinct categories from the database."""
        return [i for i in self.collection.distinct("categories") if i is not None ] # Assuming 'categories' field holds category data

    def add_category(self, hanzi: str, new_category: str) -> None:
        """Add a new category to a specific 'hanzi', creating it if it doesn't exist."""
        if new_category is None:
            return

        # Query to find the record
        query = {'hanzi': hanzi}

        update = {
            '$addToSet': {'categories': new_category}  # '$addToSet' ensures no duplicates
        }

        result = self.collection.update_one(
            query,
            update,
            upsert=True  # Create a new document if one does not exist
        )

        if result.matched_count == 0:
            print(f"Created new record for '{hanzi}' with category '{new_category}'.")
        else:
            print(f"Updated record for '{hanzi}' with category '{new_category}'.")

    def close(self) -> None:
        """Close the MongoDB connection."""
        self.client.close()