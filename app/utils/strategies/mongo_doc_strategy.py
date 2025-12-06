from typing import Dict, Any, Optional
from pymongo.synchronous.collection import Collection
from bson import ObjectId
from pymongo.errors import PyMongoError

from app.utils.interfaces.istorage_strategy import IStorageStrategy


class MongoDocumentStrategy(IStorageStrategy):
    """
    Store data directly as MongoDB documents.
    Best for: Structured data, JSON-like objects, queryable fields.
    """

    def insert(self, collection: Collection, data: Dict[str, Any]) -> str:

        try:
            if not data:
                raise ValueError("Data cannot be empty")

            result = collection.insert_one(data)
            data['_id'] = str(result.inserted_id)
            return data
            # return str(result.inserted_id)

        except PyMongoError as e:
            raise RuntimeError(f"Failed to insert document: {str(e)}")

    def get(self, collection: Collection, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Retrieve a single document matching the query.

        Args:
            collection: MongoDB collection object
            query: Query filter (e.g., {"_id": ObjectId("...")})

        Returns:
            Dictionary containing the document, or None if not found

        Raises:
            RuntimeError: If query fails
        """
        try:
            # Convert string ID to ObjectId if querying by _id
            if "_id" in query and isinstance(query["_id"], str):
                query["_id"] = ObjectId(query["_id"])

            document = collection.find_one(query)

            # Convert ObjectId to string for JSON serialization
            if document and "_id" in document:
                document["_id"] = str(document["_id"])

            return document

        except PyMongoError as e:
            raise RuntimeError(f"Failed to retrieve document: {str(e)}")

    def update(self, collection: Collection, query: Dict[str, Any], data: Dict[str, Any]) -> bool:
        """
        Update document(s) matching the query.

        Args:
            collection: MongoDB collection object
            query: Query filter to find documents to update
            data: Dictionary containing update data (will be wrapped in $set)

        Returns:
            bool: True if at least one document was modified, False otherwise

        Raises:
            ValueError: If data is invalid
            RuntimeError: If update fails
        """
        try:
            if not data:
                raise ValueError("Update data cannot be empty")

            # Convert string ID to ObjectId if querying by _id
            if "_id" in query and isinstance(query["_id"], str):
                query["_id"] = ObjectId(query["_id"])

            # Remove _id from update data if present (can't update _id)
            update_data = {k: v for k, v in data.items() if k != "_id"}

            result = collection.update_one(query, {"$set": update_data})
            return result.modified_count > 0

        except PyMongoError as e:
            raise RuntimeError(f"Failed to update document: {str(e)}")

    def delete(self, collection: Collection, query: Dict[str, Any]) -> bool:
        """
        Delete document(s) matching the query.

        Args:
            collection: MongoDB collection object
            query: Query filter to find documents to delete

        Returns:
            bool: True if at least one document was deleted, False otherwise

        Raises:
            RuntimeError: If deletion fails
        """
        try:
            # Convert string ID to ObjectId if querying by _id
            if "_id" in query and isinstance(query["_id"], str):
                query["_id"] = ObjectId(query["_id"])

            result = collection.delete_one(query)
            return result.deleted_count > 0

        except PyMongoError as e:
            raise RuntimeError(f"Failed to delete document: {str(e)}")