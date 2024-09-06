from pymongo import MongoClient
from typing import Optional, Dict, Any

class MongoDBClient:
    def __init__(self, mongo_uri: str = 'mongodb://localhost:27017/', db_name: str = 'mydatabase', collection_name: str = 'mycollection'):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]

    def find_record(self, hanzi: str) -> Optional[Dict[str, Any]]:
        """Find a record in the MongoDB collection by 'hanzi'."""
        return self.collection.find_one({'hanzi': hanzi})

    def insert_record(self, record: Dict[str, Any]) -> None:
        """Insert a new record into the MongoDB collection."""
        self.collection.insert_one(record)

    def close(self) -> None:
        """Close the MongoDB connection."""
        self.client.close()