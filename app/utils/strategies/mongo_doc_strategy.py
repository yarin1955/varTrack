# app/utils/strategies/mongo_doc_strategy.py

from typing import List, Optional, Dict
from collections import defaultdict
from pymongo import UpdateOne
from pymongo.collection import Collection
from pymongo.database import Database
from app.pipeline.pipeline_row import PipelineRow, RowKind
from app.utils.interfaces.istorage_strategy import IStorageStrategy


class MongoDocumentStrategy(IStorageStrategy):

    @staticmethod
    def write(row: Optional[PipelineRow], buffer: List[PipelineRow], db: Database, collection: Optional[Collection],
              buffer_size: int) -> None:
        # 1. Add to buffer (if a row exists)
        if row:
            buffer.append(row)

        # 2. Check if we need to flush (Buffer Full OR Force Flush)
        if len(buffer) >= buffer_size and len(buffer) > 0:
            MongoDocumentStrategy._flush(buffer, db, collection)

    @staticmethod
    def _flush(buffer: List[PipelineRow], db: Database, collection: Optional[Collection]):
        print(f"💾 [MongoDocStrategy] Flushing {len(buffer)} records...")

        # Helper to convert rows to Mongo Operations
        def create_ops(rows):
            ops = []
            for r in rows:
                doc_id = r.metadata.get('unique_key')
                if not doc_id: continue

                if r.kind == RowKind.DELETE:
                    ops.append(UpdateOne({"_id": doc_id}, {"$unset": {r.key: ""}}))
                elif r.kind in (RowKind.INSERT, RowKind.UPDATE):
                    ops.append(UpdateOne(
                        {"_id": doc_id},
                        {"$set": {r.key: r.value, "metadata": r.metadata}},
                        upsert=True
                    ))
            return ops

        try:
            # Scenario A: Static Collection (Simple)
            if collection:
                operations = create_ops(buffer)
                if operations:
                    collection.bulk_write(operations, ordered=False)

            # Scenario B: Dynamic Collection (Group by 'env')
            elif db:
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