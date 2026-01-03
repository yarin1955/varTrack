from typing import List, Optional, Dict, Any
import gridfs
import json
from collections import defaultdict
from pymongo.collection import Collection
from pymongo.database import Database
from app.pipeline.pipeline_row import PipelineRow, RowKind
from app.pipeline.sink import Sink
from app.utils.interfaces.istorage_strategy import IStorageStrategy


class MongoFileStrategy(Sink):
    """
    File-based storage strategy for MongoDB using GridFS.

    This strategy stores the entire configuration as a single file in GridFS.
    Each unique_key represents one file containing all key-value pairs.
    """

    @staticmethod
    def write(row: Optional[PipelineRow], buffer: List[PipelineRow], db: Database,
              collection: Optional[Collection], buffer_size: int) -> None:
        """
        Buffers rows and flushes when buffer size is reached.

        Args:
            row: Single row to add to buffer (None triggers flush)
            buffer: Accumulator for rows
            db: MongoDB database instance
            collection: Optional collection (used for GridFS bucket name)
            buffer_size: Number of rows to buffer before flushing (0 = flush immediately)
        """
        # Add row to buffer
        if row:
            buffer.append(row)

        # Flush when buffer is full or when explicitly triggered (buffer_size=0)
        if (len(buffer) >= buffer_size or buffer_size == 0) and len(buffer) > 0:
            MongoFileStrategy._flush(buffer, db, collection)

    @staticmethod
    def _flush(buffer: List[PipelineRow], db: Database, collection: Optional[Collection]):
        """
        Writes buffered rows to GridFS by reconstructing complete files.

        Groups rows by unique_key (filename), applies all operations,
        and stores the resulting complete document as a file.
        Supports dynamic collections based on 'env' in metadata.
        """
        try:
            # Group by target collection (if envAsCollection is enabled)
            grouped_by_collection: Dict[str, List[PipelineRow]] = defaultdict(list)

            if collection is not None:
                # Fixed collection - all rows go here
                grouped_by_collection[collection.name] = buffer
            else:
                # Dynamic collections based on env
                for row in buffer:
                    target = row.metadata.get('env') or 'fs'
                    grouped_by_collection[target].append(row)

            # Process each collection separately
            for bucket_name, rows in grouped_by_collection.items():
                fs = gridfs.GridFS(db, collection=bucket_name)

                # Group rows by filename (unique_key) within this collection
                files_to_update: Dict[str, Dict[str, Any]] = defaultdict(dict)
                metadata_map: Dict[str, Dict[str, Any]] = {}

                for row in rows:
                    filename = row.metadata.get('unique_key')
                    if not filename:
                        print(f"⚠️ [MongoFileStrategy] Skipping row without unique_key")
                        continue

                    # Store metadata (will be attached to file)
                    if filename not in metadata_map:
                        metadata_map[filename] = row.metadata

                    # Apply operation to the file's data structure
                    if row.kind == RowKind.DELETE:
                        # Mark key for deletion
                        if filename in files_to_update and row.key in files_to_update[filename]:
                            del files_to_update[filename][row.key]
                        else:
                            # Need to fetch existing file to delete key
                            files_to_update.setdefault(filename, {})
                            files_to_update[filename][f"__DELETE__{row.key}"] = None

                    elif row.kind in (RowKind.INSERT, RowKind.UPDATE, RowKind.UNCHANGED):
                        # Add or update key
                        files_to_update.setdefault(filename, {})[row.key] = row.value

                # Process each file in this collection
                for filename, updates in files_to_update.items():
                    # Fetch existing file content
                    existing_data = {}
                    existing_file = fs.find_one({"filename": filename})

                    if existing_file:
                        try:
                            content = existing_file.read()
                            if isinstance(content, bytes):
                                content = content.decode('utf-8')
                            existing_data = json.loads(content)
                        except (json.JSONDecodeError, UnicodeDecodeError) as e:
                            print(f"⚠️ [MongoFileStrategy] Error reading existing file {filename}: {e}")
                            existing_data = {}

                    # Apply updates to existing data
                    merged_data = existing_data.copy()

                    for key, value in updates.items():
                        if key.startswith("__DELETE__"):
                            # Handle deletion
                            actual_key = key.replace("__DELETE__", "")
                            merged_data.pop(actual_key, None)
                        else:
                            # Handle insert/update
                            merged_data[key] = value

                    # Delete old file if it exists
                    if existing_file:
                        fs.delete(existing_file._id)

                    # Store updated file only if there's data
                    if merged_data:
                        content_str = json.dumps(merged_data, indent=2, ensure_ascii=False)
                        content_bytes = content_str.encode('utf-8')

                        fs.put(
                            content_bytes,
                            filename=filename,
                            metadata=metadata_map.get(filename, {}),
                            content_type='application/json'
                        )

                print(f"💾 [MongoFileStrategy] Flushed {len(files_to_update)} file(s) from bucket '{bucket_name}'")

            total_files = sum(len(defaultdict(dict)) for _ in grouped_by_collection.values())
            print(
                f"💾 [MongoFileStrategy] Total: {len(buffer)} operations across {len(grouped_by_collection)} bucket(s).")

        except Exception as e:
            print(f"❌ [MongoFileStrategy] Write Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            buffer.clear()

    @staticmethod
    def fetch(metadata: dict, db: Database, collection: Optional[Collection]) -> Any:
        """
        Fetches the complete file content from GridFS.

        Args:
            metadata: Dictionary containing 'unique_key' (filename) and optionally 'env'
            db: MongoDB database instance
            collection: Optional collection (used for GridFS bucket name)

        Returns:
            Dictionary containing the file's key-value pairs, or empty dict if not found
        """
        unique_key = metadata.get('unique_key')
        env = metadata.get('env')

        if not unique_key:
            print("⚠️ [MongoFileStrategy] No unique_key in metadata for fetch")
            return {}

        try:
            # Determine GridFS bucket (support dynamic collections)
            if collection is not None:
                bucket_name = collection.name
            elif env:
                bucket_name = env
            else:
                bucket_name = 'fs'

            fs = gridfs.GridFS(db, collection=bucket_name)

            # Find file by filename
            existing_file = fs.find_one({"filename": unique_key})

            if not existing_file:
                print(f"ℹ️ [MongoFileStrategy] File not found: {unique_key}")
                return {}

            # Read and parse content
            content = existing_file.read()

            if isinstance(content, bytes):
                content = content.decode('utf-8')

            # Parse JSON content
            data = json.loads(content)

            return data

        except json.JSONDecodeError as e:
            print(f"⚠️ [MongoFileStrategy] Invalid JSON in file {unique_key}: {e}")
            return {}
        except UnicodeDecodeError as e:
            print(f"⚠️ [MongoFileStrategy] Encoding error reading file {unique_key}: {e}")
            return {}
        except Exception as e:
            print(f"⚠️ [MongoFileStrategy] Error fetching file {unique_key}: {e}")
            import traceback
            traceback.print_exc()
            return {}

    @staticmethod
    def delete(metadata: dict, db: Database, collection: Optional[Collection]) -> None:
        """
        Deletes an entire GridFS file.

        Args:
            metadata: Dictionary containing 'unique_key' (filename) and optionally 'env'
            db: MongoDB database instance
            collection: Optional collection (used for GridFS bucket name)
        """
        unique_key = metadata.get('unique_key')
        env = metadata.get('env')

        if not unique_key:
            print("⚠️ [MongoFileStrategy] Cannot delete: No unique_key in metadata")
            return

        try:
            # Determine GridFS bucket (support dynamic collections)
            if collection is not None:
                bucket_name = collection.name
            elif env:
                bucket_name = env
            else:
                bucket_name = 'fs'

            fs = gridfs.GridFS(db, collection=bucket_name)

            # Find the file
            existing_file = fs.find_one({"filename": unique_key})

            if not existing_file:
                print(f"ℹ️ [MongoFileStrategy] File not found for deletion: {unique_key}")
                return

            # Delete the file
            fs.delete(existing_file._id)
            print(f"🗑️ [MongoFileStrategy] Deleted GridFS file: {unique_key} from bucket '{bucket_name}'")

        except Exception as e:
            print(f"❌ [MongoFileStrategy] Error deleting file {unique_key}: {e}")
            import traceback
            traceback.print_exc()
            raise