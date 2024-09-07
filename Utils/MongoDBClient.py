from pymongo import MongoClient
from typing import Optional, Dict, Any
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

    def insert_record(self, record: Dict[str, Any]) -> None:
        """Insert a new record into the MongoDB collection."""
        self.collection.insert_one(record)

    def close(self) -> None:
        """Close the MongoDB connection."""
        self.client.close()