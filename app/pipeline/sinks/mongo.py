from pymongo.collection import Collection
from pymongo.database import Database
from app.models.datasources.mongo import MongoConfig
from app.pipeline.pipeline_row import PipelineRow
from app.pipeline.sink import Sink
from app.utils.enums.strategy_type import StrategyEnum
from app.utils.interfaces.istorage_strategy import IStorageStrategy
from app.utils.strategies.mongo_doc_strategy import MongoDocumentStrategy
from app.utils.strategies.mongo_file_strategy import MongoFileStrategy
from typing import Any

class MongoSink(Sink):
    def __init__(self, config: MongoConfig):
        self._config = config
        self._strategy = self._select_strategy()
        self._client = None
        self._buffer = []
        self._db: Database = None
        self._collection: Collection = None

    def _select_strategy(self) -> IStorageStrategy:
        if self._config.update_strategy == StrategyEnum.FILE:
            return MongoFileStrategy()
        return MongoDocumentStrategy()

    def connect(self) -> None:
        from pymongo import MongoClient
        options = self._config.get_pymongo_options()
        self._client = MongoClient(**options)
        self._client.admin.command('ping')
        if self._config.database:
            self._db = self._client[self._config.database]
            if self._config.collection:
                self._collection = self._db[self._config.collection]

    def disconnect(self) -> None:
        """Closes the MongoDB connection and resets internal state."""
        if self._client:
            self._client.close()
            self._client = None
            self._db = None
            self._collection = None
            print("🔌 [MongoSink] Connection closed.")

    def fetch(self, metadata: dict) -> Any:
        """Delegates state retrieval to the current strategy."""
        return self._strategy.fetch(metadata, self._db, self._collection)

    def write(self, row: PipelineRow) -> None:
        self._strategy.write(row, self._buffer, self._db, self._collection, self._config.buffer_size)

    def flush(self) -> None:
        if self._buffer:
            self._strategy.write(None, self._buffer, self._db, self._collection, 0)

    def delete(self, metadata: dict) -> None:
        """Delegates delete to the current strategy."""
        self._strategy.delete(metadata, self._db, self._collection)