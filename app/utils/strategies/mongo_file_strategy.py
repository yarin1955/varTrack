from typing import Dict, Optional, Any

from bson import ObjectId
from gridfs import GridFS
from pymongo.errors import PyMongoError
from pymongo.synchronous.collection import Collection

from app.utils.interfaces.istorage_strategy import IStorageStrategy


class MongoFileStrategy(IStorageStrategy):
    """
    Store data as files using GridFS (MongoDB's file storage system).
    Best for: Large files, binary data, images, videos, documents > 16MB.

    Note: GridFS stores files in two collections:
    - fs.files: File metadata
    - fs.chunks: File data in 255KB chunks
    """

    def __init__(self, bucket_name: str = "fs"):
        """
        Initialize FileStorageStrategy.

        Args:
            bucket_name: Name of the GridFS bucket (default: "fs")
        """
        self.bucket_name = bucket_name

    def _get_gridfs(self, collection: Collection) -> GridFS:
        """Get GridFS instance from collection's database."""
        return GridFS(collection.database, collection=self.bucket_name)

    def insert(self, collection: Collection, data: Dict[str, Any]) -> str:
        """
        Insert a file into GridFS.

        Args:
            collection: MongoDB collection object (database is used for GridFS)
            data: Dictionary with keys:
                - "filename": Name of the file
                - "content": File content (bytes or file-like object)
                - "metadata": Optional metadata dictionary
                - "content_type": Optional MIME type

        Returns:
            str: Inserted file ID as string

        Raises:
            ValueError: If required data is missing
            RuntimeError: If insertion fails
        """
        try:
            if "filename" not in data or "content" not in data:
                raise ValueError("Data must contain 'filename' and 'content'")

            fs = self._get_gridfs(collection)

            # Convert content to bytes if it's a string
            content = data["content"]
            if isinstance(content, str):
                content = content.encode('utf-8')
            elif not isinstance(content, (bytes, io.IOBase)):
                raise ValueError("Content must be bytes, string, or file-like object")

            # Prepare file parameters
            file_params = {
                "filename": data["filename"],
            }

            if "metadata" in data:
                file_params["metadata"] = data["metadata"]

            if "content_type" in data:
                file_params["content_type"] = data["content_type"]

            # Insert file
            file_id = fs.put(content, **file_params)
            return str(file_id)

        except PyMongoError as e:
            raise RuntimeError(f"Failed to insert file: {str(e)}")

    def get(self, collection: Collection, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Retrieve a file from GridFS.

        Args:
            collection: MongoDB collection object
            query: Query filter, typically {"_id": file_id} or {"filename": "name"}

        Returns:
            Dictionary containing:
                - "_id": File ID
                - "filename": Filename
                - "length": File size in bytes
                - "upload_date": Upload timestamp
                - "content_type": MIME type (if set)
                - "metadata": Metadata (if set)
                - "content": File content as bytes
            Or None if not found

        Raises:
            RuntimeError: If retrieval fails
        """
        try:
            fs = self._get_gridfs(collection)

            # Convert string ID to ObjectId if querying by _id
            if "_id" in query and isinstance(query["_id"], str):
                query["_id"] = ObjectId(query["_id"])

            # Find file in GridFS
            grid_out = None
            if "_id" in query:
                try:
                    grid_out = fs.get(query["_id"])
                except:
                    return None
            elif "filename" in query:
                grid_out = fs.find_one({"filename": query["filename"]})
            else:
                grid_out = fs.find_one(query)

            if not grid_out:
                return None

            # Build response dictionary
            result = {
                "_id": str(grid_out._id),
                "filename": grid_out.filename,
                "length": grid_out.length,
                "upload_date": grid_out.upload_date,
                "content": grid_out.read()
            }

            if hasattr(grid_out, 'content_type') and grid_out.content_type:
                result["content_type"] = grid_out.content_type

            if hasattr(grid_out, 'metadata') and grid_out.metadata:
                result["metadata"] = grid_out.metadata

            return result

        except PyMongoError as e:
            raise RuntimeError(f"Failed to retrieve file: {str(e)}")

    def update(self, collection: Collection, query: Dict[str, Any], data: Dict[str, Any]) -> bool:
        """
        Update a file in GridFS (by deleting and reinserting).
        GridFS doesn't support in-place updates, so we delete and reinsert.

        Args:
            collection: MongoDB collection object
            query: Query filter to find the file to update
            data: Dictionary with new file data (same format as insert)

        Returns:
            bool: True if file was updated, False otherwise

        Raises:
            ValueError: If data is invalid
            RuntimeError: If update fails
        """
        try:
            # First, check if file exists
            existing = self.get(collection, query)
            if not existing:
                return False

            # Delete the old file
            self.delete(collection, query)

            # Preserve original filename if not provided
            if "filename" not in data:
                data["filename"] = existing["filename"]

            # Insert the new file
            self.insert(collection, data)
            return True

        except Exception as e:
            raise RuntimeError(f"Failed to update file: {str(e)}")

    def delete(self, collection: Collection, query: Dict[str, Any]) -> bool:
        """
        Delete a file from GridFS.

        Args:
            collection: MongoDB collection object
            query: Query filter, typically {"_id": file_id} or {"filename": "name"}

        Returns:
            bool: True if file was deleted, False otherwise

        Raises:
            RuntimeError: If deletion fails
        """
        try:
            fs = self._get_gridfs(collection)

            # Convert string ID to ObjectId if querying by _id
            if "_id" in query and isinstance(query["_id"], str):
                query["_id"] = ObjectId(query["_id"])

            # Find and delete file
            if "_id" in query:
                try:
                    fs.delete(query["_id"])
                    return True
                except:
                    return False
            elif "filename" in query:
                grid_out = fs.find_one({"filename": query["filename"]})
                if grid_out:
                    fs.delete(grid_out._id)
                    return True
                return False
            else:
                # For other queries, find first match and delete
                grid_out = fs.find_one(query)
                if grid_out:
                    fs.delete(grid_out._id)
                    return True
                return False

        except PyMongoError as e:
            raise RuntimeError(f"Failed to delete file: {str(e)}")
