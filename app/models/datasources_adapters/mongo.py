
from typing import Any
from pymongo import MongoClient
import gridfs

from app.models.datasources.mongo import MongoConfig
from app.models.ds_adapter import DataSourceAdapter
from app.utils.enums.strategy_type import StrategyEnum
from app.utils.factories.ds_adapter_factory import DSAdapterFactory
from app.utils.interfaces.istorage_strategy import IStorageStrategy
from app.utils.strategies.document_strategy import DocumentStorageStrategy
from app.utils.strategies.file_strategy import FileStorageStrategy


@DSAdapterFactory.register()
class MongoAdapter(DataSourceAdapter):


    def __init__(self, config: MongoConfig):
        self._config = config

        self._strategy= self._select_strategy(config)

    def _select_strategy(self, config: MongoConfig) -> IStorageStrategy:
        if config.update_strategy == StrategyEnum.FILE:
            return FileStorageStrategy()
        # default (also covers MongoStorageStrategy.DOCUMENT)
        return DocumentStorageStrategy()

    def connect(self):
        try:
            from pymongo import MongoClient
            from pymongo.errors import ConnectionFailure, ConfigurationError

            # Get PyMongo connection options from config
            options = self._config.get_pymongo_options()

            # Create MongoClient with the options
            self._client = MongoClient(**options)

            # Test the connection by pinging the server
            self._client.admin.command('ping')

            return self._client

        except ConnectionFailure as e:
            raise ConnectionError(f"Failed to connect to MongoDB: {str(e)}")
        except ConfigurationError as e:
            raise ValueError(f"Invalid MongoDB configuration: {str(e)}")
        except Exception as e:
            raise ConnectionError(f"Unexpected error connecting to MongoDB: {str(e)}")


    def insert(self, *args: Any, **kwargs: Any) -> None:
        """Dispatch insert based on arguments."""
        if len(args) == 2 and isinstance(args[0], str) and isinstance(args[1], dict):
            self._insert_document(args[0], args[1])
        elif len(args) == 2 and isinstance(args[0], str) and isinstance(args[1], bytes):
            self._insert_file(args[0], args[1])

    def get(self, *args: Any, **kwargs: Any) -> Any:
        """Dispatch get based on arguments."""
        if len(args) == 2 and isinstance(args[1], dict):
            return self._get_document(args[0], args[1])
        elif len(args) == 1:
            return self._get_file(args[0])

    def update(self, *args: Any, **kwargs: Any) -> None:
        """Dispatch update based on arguments."""
        if len(args) == 3 and isinstance(args[2], dict):
            self._update_document(args[0], args[1], args[2])
        elif len(args) == 2 and isinstance(args[1], bytes):
            self._update_file(args[0], args[1])

    def delete(self, *args: Any, **kwargs: Any) -> None:
        """Dispatch delete based on arguments."""
        if len(args) == 2 and isinstance(args[1], dict):
            self._delete_document(args[0], args[1])
        elif len(args) == 1:
            self._delete_file(args[0])

    def _insert_document(self, collection: str, document: dict) -> None:
        """Insert document into collection."""
        self.db[collection].insert_one(document)

    def _get_document(self, collection: str, query: dict) -> dict | None:
        """Find one document matching query."""
        return self.db[collection].find_one(query)

    def _update_document(self, collection: str, query: dict, update: dict) -> None:
        """Update one document matching query."""
        self.db[collection].update_one(query, {"$set": update})

    def _delete_document(self, collection: str, query: dict) -> None:
        """Delete documents matching query using delete_many."""
        self.db[collection].delete_many(query)

    def _insert_file(self, path: str, content: bytes) -> None:
        """Store file in GridFS."""
        self.fs.put(content, filename=path)

    def _get_file(self, path: str) -> bytes | None:
        """Retrieve file from GridFS by filename."""
        try:
            grid_out = self.fs.find_one({"filename": path})
            return grid_out.read() if grid_out else None
        except Exception:
            return None

    def _update_file(self, path: str, content: bytes) -> None:
        """Replace file content by deleting old and inserting new."""
        self._delete_file(path)
        self._insert_file(path, content)

    def _delete_file(self, path: str) -> None:
        """Delete file from GridFS by filename."""
        grid_out = self.fs.find_one({"filename": path})
        if grid_out:
            self.fs.delete(grid_out._id)