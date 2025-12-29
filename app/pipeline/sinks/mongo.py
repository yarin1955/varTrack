from pymongo import InsertOne, UpdateOne, DeleteOne
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import BulkWriteError

from app.models.datasources.mongo import MongoConfig
from app.pipeline.pipeline_row import PipelineRow, RowKind
from app.pipeline.sink import Sink
from app.utils.enums.strategy_type import StrategyEnum
from app.utils.interfaces.istorage_strategy import IStorageStrategy
from app.utils.strategies.mongo_doc_strategy import MongoDocumentStrategy
from app.utils.strategies.mongo_file_strategy import MongoFileStrategy


class MongoSink(Sink):
    def __init__(self, config: MongoConfig):
        self._config = config
        self._strategy = self._select_strategy()
        self._client = None
        self._buffer = []
        # Initialize placeholders for the actual PyMongo objects
        self._db: Database = None
        self._collection: Collection = None

    def _select_strategy(self) -> IStorageStrategy:
        if self._config.update_strategy == StrategyEnum.FILE:
            return MongoFileStrategy()
        return MongoDocumentStrategy()

    def connect(self) -> None:
        from pymongo import MongoClient
        from pymongo.errors import ConnectionFailure, OperationFailure

        try:
            # 1. Get PyMongo specific options from the config helper
            options = self._config.get_pymongo_options()

            # 2. Initialize the Client
            self._client = MongoClient(**options)

            # 3. Verify connectivity immediately (fail fast)
            self._client.admin.command('ping')
            print(f"✅ [MongoSink] Successfully connected to MongoDB at {self._config.host}:{self._config.port}")

            # 4. Select Database
            if self._config.database:
                self._db = self._client[self._config.database]

                # 5. Select/Create Collection (Only if a static collection name is provided)
                if self._config.collection:
                    col_name = self._config.collection

                    # Check if we need to apply specific creation options
                    col_options = self._config.get_collection_options()

                    if col_options:
                        existing_cols = self._db.list_collection_names()
                        if col_name not in existing_cols:
                            print(f"⚙️ [MongoSink] Creating collection '{col_name}' with specific options.")
                            self._db.create_collection(col_name, **col_options)

                    # Set the collection reference
                    self._collection = self._db[col_name]

            elif not self._config.envAsCollection:
                print("⚠️ [MongoSink] No database specified in config.")

        except (ConnectionFailure, OperationFailure) as e:
            print(f"❌ [MongoSink] Failed to connect to MongoDB: {e}")
            raise e
        except Exception as e:
            print(f"❌ [MongoSink] Unexpected error during connection: {e}")
            raise e

    def write(self, row: PipelineRow) -> None:
        """
        Delegate the entire write logic to the strategy.
        """
        # FIX 1: Pass the actual PyMongo objects (self._db, self._collection), not the config strings
        self._strategy.write(
            row=row,
            buffer=self._buffer,
            db=self._db,
            collection=self._collection,
            buffer_size=self._config.buffer_size
        )

    def flush(self) -> None:
        """
        Force flush any remaining items in the buffer.
        """
        if self._buffer:
            # FIX 2: Pass buffer_size=0 to force the strategy to flush immediately
            # FIX 3: Pass actual PyMongo objects here as well
            self._strategy.write(
                row=None,
                buffer=self._buffer,
                db=self._db,
                collection=self._collection,
                buffer_size=0  # Force flush
            )