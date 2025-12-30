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

    def read(self, metadata: dict) -> Any:
        """
        Fetches current state and strips internal fields to avoid fake flushes.
        """
        unique_key = metadata.get('unique_key')
        env = metadata.get('env')

        if self._config.update_strategy == StrategyEnum.FILE:
            try:
                import gridfs
                fs = gridfs.GridFS(self._db, collection=self._collection.name if self._collection else 'fs')
                existing = fs.find_one({"filename": unique_key})
                return existing.read().decode('utf-8') if existing else None
            except: return None
        else:
            try:
                # Explicit identity check to avoid PyMongo truth-value errors
                coll = self._collection
                if coll is None and self._db is not None and env:
                    coll = self._db[env]

                if coll is not None:
                    doc = coll.find_one({"_id": unique_key})
                    if doc:
                        # STRIP INTERNAL FIELDS to prevent false diffs
                        doc.pop('_id', None)
                        doc.pop('metadata', None)
                    return doc or {}
            except Exception as e:
                print(f"⚠️ [MongoSink] Error reading document: {e}")
                return {}

    def write(self, row: PipelineRow) -> None:
        self._strategy.write(row, self._buffer, self._db, self._collection, self._config.buffer_size)

    def flush(self) -> None:
        if self._buffer:
            self._strategy.write(None, self._buffer, self._db, self._collection, 0)