from pymongo import InsertOne, UpdateOne, DeleteOne
from pymongo.collection import Collection
from pymongo.errors import BulkWriteError
from app.pipeline.core import Sink
from app.pipeline.models import PipelineRow, RowKind

class MongoSink(Sink):
    def __init__(self, collection: Collection, is_upsert_enable: bool = False, batch_size: int = 1000):
        """
        Args:
            collection: PyMongo Collection object.
            is_upsert_enable: If True, uses UpdateOne(upsert=True). If False, uses InsertOne.
            batch_size: Number of rows to buffer before flushing.
        """
        self.collection = collection
        self.upsert_enable = is_upsert_enable
        self.batch_size = batch_size
        self._buffer = []

    def write(self, row: PipelineRow) -> None:
        op = None

        if row.kind == RowKind.DELETE:
            op = DeleteOne({"_id": row.key})

        elif row.kind in (RowKind.INSERT, RowKind.UPDATE):
            if self.upsert_enable:
                # Idempotent write (Safe)
                op = UpdateOne(
                    {"_id": row.key},
                    {"$set": {"value": row.value, "metadata": row.metadata}},
                    upsert=True
                )
            else:
                # Strict Insert (Will fail on duplicates)
                op = InsertOne({
                    "_id": row.key,
                    "value": row.value,
                    "metadata": row.metadata
                })

        if op:
            self._buffer.append(op)
            if len(self._buffer) >= self.batch_size:
                self.flush()

    def flush(self) -> None:
        if not self._buffer:
            return

        try:
            print(f"💾 [MongoSink] Flushing {len(self._buffer)} rows...")
            # ordered=False allows parallel writes and doesn't stop on first error
            self.collection.bulk_write(self._buffer, ordered=False)
        except BulkWriteError as bwe:
            # Log errors (e.g. duplicate keys when upsert=False)
            print(f"⚠️ [MongoSink] Bulk Write Error: {bwe.details.get('writeErrors')[:2]} ... (truncated)")
        except Exception as e:
            print(f"❌ [MongoSink] Flush failed: {e}")
        finally:
            self._buffer.clear()