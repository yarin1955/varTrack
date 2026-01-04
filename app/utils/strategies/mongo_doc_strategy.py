from typing import List, Optional, Any
from collections import defaultdict
from pymongo import UpdateOne
from pymongo.collection import Collection
from pymongo.database import Database
from app.pipeline.pipeline_row import PipelineRow, RowKind
from app.pipeline.sink import Sink
from app.utils.interfaces.istorage_strategy import IStorageStrategy

class MongoDocumentStrategy(Sink):
    @staticmethod
    def write(row: Optional[PipelineRow], buffer: List[PipelineRow], db: Database,
              collection: Optional[Collection], buffer_size: int) -> None:
        if row:
            buffer.append(row)
        if (len(buffer) >= buffer_size or buffer_size == 0) and len(buffer) > 0:
            MongoDocumentStrategy._flush(buffer, db, collection)

    @staticmethod
    def _flush(buffer: List[PipelineRow], db: Database, collection: Optional[Collection]):
        def create_ops(rows):
            ops = []
            for r in rows:
                doc_id = r.metadata.get('unique_key')
                # SKIP if doc_id is missing or if key is immutable '_id'
                if not doc_id or r.key == '_id':
                    continue

                if r.kind == RowKind.DELETE:
                    ops.append(UpdateOne({"_id": doc_id}, {"$unset": {r.key: ""}}))
                elif r.kind in (RowKind.INSERT, RowKind.UPDATE):
                    # Refreshes 'metadata' on every write
                    ops.append(UpdateOne(
                        {"_id": doc_id},
                        {"$set": {r.key: r.value, "metadata": r.metadata}},
                        upsert=True
                    ))
            return ops

        try:
            if collection is not None:
                operations = create_ops(buffer)
                if operations:
                    collection.bulk_write(operations, ordered=False)
            elif db is not None:
                grouped = defaultdict(list)
                for r in buffer:
                    target = r.metadata.get('env') or r.metadata.get('collection')
                    if target: grouped[target].append(r)

                for col_name, rows in grouped.items():
                    ops = create_ops(rows)
                    if ops:
                        db[col_name].bulk_write(ops, ordered=False)
        except Exception as e:
            print(f"❌ [MongoDocStrategy] Write Error: {e}")
        finally:
            buffer.clear()

    @staticmethod
    def fetch(metadata: dict, db: Database, collection: Optional[Collection]) -> Any:
        unique_key = metadata.get('unique_key')
        env = metadata.get('env')

        try:
            coll = collection
            if coll is None and db is not None and env:
                coll = db[env]

            if coll is not None:
                doc = coll.find_one({"_id": unique_key})
                if doc:
                    doc.pop('_id', None)
                    doc.pop('metadata', None)
                return doc or {}
        except Exception as e:
            print(f"⚠️ [MongoDocStrategy] Error fetching document: {e}")
            return {}
        return {}

    @staticmethod
    def delete(metadata: dict, db: Database, collection: Optional[Collection]) -> None:

        unique_key = metadata.get('unique_key')
        env = metadata.get('env')

        if not unique_key:
            print("⚠️ [MongoDocStrategy] Cannot delete: No unique_key in metadata")
            return

        try:
            # Determine target collection
            target_collection = collection
            if target_collection is None and db is not None and env:
                target_collection = db[env]

            if target_collection is None:
                print(f"⚠️ [MongoDocStrategy] Cannot delete {unique_key}: No collection specified")
                return

            # Delete the document
            result = target_collection.delete_one({"_id": unique_key})

            if result.deleted_count > 0:
                print(
                    f"🗑️ [MongoDocStrategy] Deleted document: {unique_key} from collection '{target_collection.name}'")
            else:
                print(f"ℹ️ [MongoDocStrategy] Document not found for deletion: {unique_key}")

        except Exception as e:
            print(f"❌ [MongoDocStrategy] Error deleting {unique_key}: {e}")
            raise