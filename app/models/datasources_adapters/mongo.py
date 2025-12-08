
from typing import Any

from app.models.datasources.mongo import MongoConfig
from app.models.ds_adapter import DataSourceAdapter
from app.utils.enums.strategy_type import StrategyEnum
from app.utils.factories.ds_adapter_factory import DSAdapterFactory
from app.utils.interfaces.istorage_strategy import IStorageStrategy
from app.utils.strategies.mongo_doc_strategy import MongoDocumentStrategy
from app.utils.strategies.mongo_file_strategy import MongoFileStrategy


@DSAdapterFactory.register()
class MongoAdapter(DataSourceAdapter):


    def __init__(self, config: MongoConfig):
        self._config = config
        self._strategy = self._select_strategy(config)
        self._client = None
        self._collection = None  # Add this to store the collection object

    def _select_strategy(self, config: MongoConfig) -> IStorageStrategy:
        if config.update_strategy == StrategyEnum.FILE:
            return MongoFileStrategy()
        return MongoDocumentStrategy()

    def connect(self):
        try:
            from pymongo import MongoClient
            from pymongo.errors import ConnectionFailure, ConfigurationError

            options = self._config.get_pymongo_options()
            self._client = MongoClient(**options)
            self._client.admin.command('ping')

            # Get the actual collection object
            db = self._client[self._config.database]  # Assuming config has database name
            self._collection = db[self._config.collection]

            return self._client

        except ConnectionFailure as e:
            raise ConnectionError(f"Failed to connect to MongoDB: {str(e)}")
        except ConfigurationError as e:
            raise ValueError(f"Invalid MongoDB configuration: {str(e)}")
        except Exception as e:
            raise ConnectionError(f"Unexpected error connecting to MongoDB: {str(e)}")

    def insert(self, data) -> None:
        """Dispatch insert based on arguments."""
        if self._collection is None:
            raise RuntimeError("Not connected to MongoDB. Call connect() first.")
        # Pass the collection object, not the string
        self._strategy.insert(self._collection, data)

    def upsert(self, data: Any) -> None:

        if self._collection is None:
            raise RuntimeError("Not connected to MongoDB. Call connect() first.")

        self._strategy.upsert(self._collection, data)

    def get(self, data) -> Any:
        """Dispatch get based on arguments."""
        self._strategy.get(self._collection, data)

    def update(self, data) -> Any:
        """Dispatch get based on arguments."""
        self._strategy.update(self._collection, data)

    def delete(self, data) -> Any:
        """Dispatch get based on arguments."""
        self._strategy.delete(self._collection, data)
