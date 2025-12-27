# app/utils/strategies/mongo_file_strategy.py

from typing import List, Optional
import gridfs
from pymongo.collection import Collection
from pymongo.database import Database
from app.pipeline.pipeline_row import PipelineRow, RowKind
from app.utils.interfaces.istorage_strategy import IStorageStrategy


class MongoFileStrategy(IStorageStrategy):

    @staticmethod
    def write(row: Optional[PipelineRow], buffer: List[PipelineRow], db: Database, collection: Optional[Collection],
              buffer_size: int) -> None:
        # 1. Add to buffer
        if row:
            buffer.append(row)

        # 2. Check if flush needed
        if len(buffer) >= buffer_size and len(buffer) > 0:
            MongoFileStrategy._flush(buffer, db, collection)

    @staticmethod
    def _flush(buffer: List[PipelineRow], db: Database, collection: Optional[Collection]):
        try:
            # Determine the GridFS bucket
            # If dynamic, we default to 'fs' or we could calculate per row, 
            # but usually GridFS is centralized. Let's assume 'fs' if dynamic.
            bucket_name = collection.name if collection else 'fs'
            fs = gridfs.GridFS(db, collection=bucket_name)

            for r in buffer:
                filename = r.metadata.get('unique_key')
                if not filename: continue

                # Delete existing (GridFS doesn't support update, only replace)
                existing = fs.find_one({"filename": filename})
                if existing:
                    fs.delete(existing._id)

                if r.kind in (RowKind.INSERT, RowKind.UPDATE):
                    # Ensure content is bytes
                    content = r.value
                    if isinstance(content, str):
                        content = content.encode('utf-8')
                    elif not isinstance(content, bytes):
                        content = str(content).encode('utf-8')

                    fs.put(content, filename=filename, metadata=r.metadata)

            print(f"💾 [MongoFileStrategy] Flushed {len(buffer)} files.")

        except Exception as e:
            print(f"❌ [MongoFileStrategy] Write Error: {e}")
        finally:
            buffer.clear()