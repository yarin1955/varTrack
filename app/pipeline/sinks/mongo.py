from pymongo import InsertOne, UpdateOne, DeleteOne
from pymongo.collection import Collection
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
            # 'ping' command is lightweight and verifies Auth + Network
            self._client.admin.command('ping')
            print(f"✅ [MongoSink] Successfully connected to MongoDB at {self._config.host}:{self._config.port}")

            # 4. Select Database
            if self._config.database:
                self._db = self._client[self._config.database]

                # 5. Select/Create Collection (Only if a static collection name is provided)
                if self._config.collection:
                    col_name = self._config.collection

                    # Check if we need to apply specific creation options
                    # (e.g., TimeSeries, Capped, Validators)
                    col_options = self._config.get_collection_options()

                    if col_options:
                        # We must check existence, otherwise create_collection raises an error if it exists
                        existing_cols = self._db.list_collection_names()

                        if col_name not in existing_cols:
                            print(f"⚙️ [MongoSink] Creating collection '{col_name}' with specific options.")
                            self._db.create_collection(col_name, **col_options)

                    # Set the collection reference for the flush method
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
        The strategy will handle buffering and flushing.
        """
        self._strategy.write(
            row=row,
            buffer=self._buffer,
            db=self._config.database,
            collection=self._config.collection,
            buffer_size=self._config.buffer_size
        )

    def flush(self) -> None:
        """
        Force flush any remaining items in the buffer.
        """
        if self._buffer:
            # We call the strategy with buffer_size=0 to force a flush
            self._strategy.write(
                row=None,  # No new row, just flush existing
                buffer=self._buffer,
                db=self._config.database,
                collection=self._config.collection,
                buffer_size=self._config.buffer_size
            )

