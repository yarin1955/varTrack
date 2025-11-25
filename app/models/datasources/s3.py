# class MongoStorage:
#     """High-level storage class for MongoDB operations."""
#
#     def __init__(self, adapter: MongoAdapter, strategy_type: str) -> None:
#         """Initialize with MongoAdapter and strategy type ('document' or 'file')."""
#         if strategy_type not in ("document", "file"):
#             raise ValueError("strategy_type must be 'document' or 'file'")
#         self.adapter = adapter
#         self.strategy_type = strategy_type
#
#     def insert(self, *args: Any) -> None:
#         """Insert document or file based on strategy type."""
#         self.adapter.insert(*args)
#
#     def get(self, *args: Any) -> Any:
#         """Get document or file based on strategy type."""
#         return self.adapter.get(*args)
#
#     def update(self, *args: Any) -> None:
#         """Update document or file based on strategy type."""
#         self.adapter.update(*args)
#
#     def delete(self, *args: Any) -> None:
#         """Delete document or file based on strategy type."""
#         self.adapter.delete(*args)

# class DatasourceTypeA(BaseModel):
#     type: Literal["typeA"] = "typeA"
#     name: str
#     update_strategy: Literal[UpdateStrategy.KV, UpdateStrategy.FILE]

# def __init__(self):
#     self._strategy = KeyValueStorageStrategy()
#     print("[Zookeeper] Initialized with KeyValueStorageStrategy")

# _strategy = KeyValueStorageStrategy()
# @model_validator(mode="after")
# def set_default_strategy(self):
#     if self.strategy is None:
#         self.strategy = high_strategy if self.x > 5 else low_strategy
#     return self
# class Mongo:
#     """Mongo class that supports File and Document storage strategies"""
#
#     strategy_type = "file"  # Class variable with default value
#
#     def __init__(self):
#         """Initialize Mongo with the current strategy type"""
#         self._strategy = self._create_strategy()
#         print(f"[Mongo] Initialized with strategy type: '{self.strategy_type}'")
#
#     def _create_strategy(self) -> StorageStrategy:
#         """Create the appropriate strategy based on strategy_type"""
#         if self.strategy_type == "file":
#             return FileStorageStrategy(base_path="./storage/mongo_files")
#         elif self.strategy_type == "document":
#             return DocumentStorageStrategy(base_path="./storage/mongo_documents")
#         else:
#             raise ValueError(f"Invalid strategy type: '{self.strategy_type}'. Use 'file' or 'document'")
#
#     def set_strategy_type(self, strategy_type: str):
#         """Change the strategy type at runtime"""
#         self.strategy_type = strategy_type.lower()
#         print(f"\n[Mongo] Changing strategy type to: '{self.strategy_type}'")
#         self._strategy = self._create_strategy()


# from abc import ABC, abstractmethod
# from typing import Any
# import redis
# from kazoo.client import KazooClient
# from pymongo import MongoClient
# import gridfs
#
#
# class StorageStrategy(ABC):
#     """Base strategy interface for all storage operations."""
#
#     @abstractmethod
#     def insert(self, *args: Any, **kwargs: Any) -> None:
#         """Insert data into storage."""
#         pass
#
#     @abstractmethod
#     def get(self, *args: Any, **kwargs: Any) -> Any:
#         """Retrieve data from storage."""
#         pass
#
#     @abstractmethod
#     def update(self, *args: Any, **kwargs: Any) -> None:
#         """Update data in storage."""
#         pass
#
#     @abstractmethod
#     def delete(self, *args: Any, **kwargs: Any) -> None:
#         """Delete data from storage."""
#         pass
#
#
# class KeyValueStorageStrategy(StorageStrategy):
#     """Strategy for key-value storage operations."""
#
#     @abstractmethod
#     def insert(self, key: str, value: str) -> None:
#         """Insert or set a key-value pair."""
#         pass
#
#     @abstractmethod
#     def get(self, key: str) -> str | None:
#         """Get value by key, returns None if not found."""
#         pass
#
#     @abstractmethod
#     def update(self, items: dict[str, str]) -> None:
#         """Bulk update multiple key-value pairs. Creates keys if missing."""
#         pass
#
#     @abstractmethod
#     def delete(self, keys: list[str]) -> None:
#         """Bulk delete multiple keys. Ignores missing keys."""
#         pass
#
#
# class DocumentStorageStrategy(StorageStrategy):
#     """Strategy for document-oriented storage operations."""
#
#     @abstractmethod
#     def insert(self, collection: str, document: dict) -> None:
#         """Insert a document into a collection."""
#         pass
#
#     @abstractmethod
#     def get(self, collection: str, query: dict) -> dict | None:
#         """Retrieve a document matching the query."""
#         pass
#
#     @abstractmethod
#     def update(self, collection: str, query: dict, update: dict) -> None:
#         """Update a document matching the query."""
#         pass
#
#     @abstractmethod
#     def delete(self, collection: str, query: dict) -> None:
#         """Delete document(s) matching the query."""
#         pass
#
#
# class FileStorageStrategy(StorageStrategy):
#     """Strategy for file/blob storage operations."""
#
#     @abstractmethod
#     def insert(self, path: str, content: bytes) -> None:
#         """Insert file content at path."""
#         pass
#
#     @abstractmethod
#     def get(self, path: str) -> bytes | None:
#         """Retrieve file content by path."""
#         pass
#
#     @abstractmethod
#     def update(self, path: str, content: bytes) -> None:
#         """Update file content at path."""
#         pass
#
#     @abstractmethod
#     def delete(self, path: str) -> None:
#         """Delete file at path."""
#         pass
#
#
# class RedisAdapter(KeyValueStorageStrategy):
#     """Adapter for Redis backend implementing key-value operations."""
#
#     def __init__(self, client: redis.Redis) -> None:
#         """Initialize with Redis client."""
#         self.client = client
#
#     def insert(self, key: str, value: str) -> None:
#         """Set key-value pair using Redis SET."""
#         self.client.set(key, value)
#
#     def get(self, key: str) -> str | None:
#         """Get value by key, returns None if not found."""
#         result = self.client.get(key)
#         return result.decode('utf-8') if result else None
#
#     def update(self, items: dict[str, str]) -> None:
#         """Bulk update using Redis MSET. Creates keys if missing."""
#         if items:
#             self.client.mset(items)
#
#     def delete(self, keys: list[str]) -> None:
#         """Bulk delete using Redis DEL. Ignores missing keys."""
#         if keys:
#             self.client.delete(*keys)
#
#
# class ZookeeperAdapter(KeyValueStorageStrategy):
#     """Adapter for ZooKeeper backend implementing key-value operations."""
#
#     def __init__(self, client: KazooClient, prefix: str = "/app__save") -> None:
#         """Initialize with KazooClient and path prefix."""
#         self.client = client
#         self.prefix = prefix
#
#     def _get_path(self, key: str) -> str:
#         """Convert key to ZooKeeper path."""
#         return f"{self.prefix}/{key}"
#
#     def insert(self, key: str, value: str) -> None:
#         """Create znode with data. Overwrites if exists."""
#         path = self._get_path(key)
#         if self.client.exists(path):
#             self.client.set(path, value.encode('utf-8'))
#         else:
#             self.client.create(path, value.encode('utf-8'), makepath=True)
#
#     def get(self, key: str) -> str | None:
#         """Get znode data as string, returns None if not found."""
#         path = self._get_path(key)
#         if self.client.exists(path):
#             data, _ = self.client.get(path)
#             return data.decode('utf-8')
#         return None
#
#     def update(self, items: dict[str, str]) -> None:
#         """Bulk update using Kazoo transaction. Creates nodes if missing."""
#         if not items:
#             return
#
#         transaction = self.client.transaction()
#         for key, value in items.items():
#             path = self._get_path(key)
#             if self.client.exists(path):
#                 transaction.set_data(path, value.encode('utf-8'))
#             else:
#                 transaction.create(path, value.encode('utf-8'), makepath=True)
#         transaction.commit()
#
#     def delete(self, keys: list[str]) -> None:
#         """Bulk delete using Kazoo transaction. Ignores missing keys."""
#         if not keys:
#             return
#
#         transaction = self.client.transaction()
#         for key in keys:
#             path = self._get_path(key)
#             if self.client.exists(path):
#                 transaction.delete(path)
#         transaction.commit()
#
#
# class MongoAdapter(DocumentStorageStrategy, FileStorageStrategy):
#     """Adapter for MongoDB implementing both document and file operations."""
#
#     def __init__(self, client: MongoClient, database: str) -> None:
#         """Initialize with MongoClient and database name."""
#         self.client = client
#         self.db = self.client[database]
#         self.fs = gridfs.GridFS(self.db)
#
#     def insert(self, *args: Any, **kwargs: Any) -> None:
#         """Dispatch insert based on arguments."""
#         if len(args) == 2 and isinstance(args[0], str) and isinstance(args[1], dict):
#             self._insert_document(args[0], args[1])
#         elif len(args) == 2 and isinstance(args[0], str) and isinstance(args[1], bytes):
#             self._insert_file(args[0], args[1])
#
#     def get(self, *args: Any, **kwargs: Any) -> Any:
#         """Dispatch get based on arguments."""
#         if len(args) == 2 and isinstance(args[1], dict):
#             return self._get_document(args[0], args[1])
#         elif len(args) == 1:
#             return self._get_file(args[0])
#
#     def update(self, *args: Any, **kwargs: Any) -> None:
#         """Dispatch update based on arguments."""
#         if len(args) == 3 and isinstance(args[2], dict):
#             self._update_document(args[0], args[1], args[2])
#         elif len(args) == 2 and isinstance(args[1], bytes):
#             self._update_file(args[0], args[1])
#
#     def delete(self, *args: Any, **kwargs: Any) -> None:
#         """Dispatch delete based on arguments."""
#         if len(args) == 2 and isinstance(args[1], dict):
#             self._delete_document(args[0], args[1])
#         elif len(args) == 1:
#             self._delete_file(args[0])
#
#     def _insert_document(self, collection: str, document: dict) -> None:
#         """Insert document into collection."""
#         self.db[collection].insert_one(document)
#
#     def _get_document(self, collection: str, query: dict) -> dict | None:
#         """Find one document matching query."""
#         return self.db[collection].find_one(query)
#
#     def _update_document(self, collection: str, query: dict, update: dict) -> None:
#         """Update one document matching query."""
#         self.db[collection].update_one(query, {"$set": update})
#
#     def _delete_document(self, collection: str, query: dict) -> None:
#         """Delete documents matching query using delete_many."""
#         self.db[collection].delete_many(query)
#
#     def _insert_file(self, path: str, content: bytes) -> None:
#         """Store file in GridFS."""
#         self.fs.put(content, filename=path)
#
#     def _get_file(self, path: str) -> bytes | None:
#         """Retrieve file from GridFS by filename."""
#         try:
#             grid_out = self.fs.find_one({"filename": path})
#             return grid_out.read() if grid_out else None
#         except Exception:
#             return None
#
#     def _update_file(self, path: str, content: bytes) -> None:
#         """Replace file content by deleting old and inserting new."""
#         self._delete_file(path)
#         self._insert_file(path, content)
#
#     def _delete_file(self, path: str) -> None:
#         """Delete file from GridFS by filename."""
#         grid_out = self.fs.find_one({"filename": path})
#         if grid_out:
#             self.fs.delete(grid_out._id)
#
#
# class RedisStorage:
#     """High-level storage class for key-value operations."""
#
#     def __init__(self, strategy: KeyValueStorageStrategy) -> None:
#         """Initialize with key-value strategy."""
#         self.strategy = strategy
#
#     def set(self, key: str, value: str) -> None:
#         """Set single key-value pair."""
#         self.strategy.insert(key, value)
#
#     def get(self, key: str) -> str | None:
#         """Get value by key."""
#         return self.strategy.get(key)
#
#     def update(self, items: dict[str, str]) -> None:
#         """Bulk update multiple key-value pairs."""
#         self.strategy.update(items)
#
#     def delete(self, keys: list[str]) -> None:
#         """Bulk delete multiple keys."""
#         self.strategy.delete(keys)
#
#
# class ZookeeperStorage:
#     """High-level storage class for ZooKeeper operations."""
#
#     def __init__(self, strategy: KeyValueStorageStrategy) -> None:
#         """Initialize with key-value strategy."""
#         self.strategy = strategy
#
#     def set(self, key: str, value: str) -> None:
#         """Set single key-value pair."""
#         self.strategy.insert(key, value)
#
#     def get(self, key: str) -> str | None:
#         """Get value by key."""
#         return self.strategy.get(key)
#
#     def update(self, items: dict[str, str]) -> None:
#         """Bulk update multiple key-value pairs."""
#         self.strategy.update(items)
#
#     def delete(self, keys: list[str]) -> None:
#         """Bulk delete multiple keys."""
#         self.strategy.delete(keys)
#
#
# class MongoStorage:
#     """High-level storage class for MongoDB operations."""
#
#     def __init__(self, adapter: MongoAdapter, strategy_type: str) -> None:
#         """Initialize with MongoAdapter and strategy type ('document' or 'file')."""
#         if strategy_type not in ("document", "file"):
#             raise ValueError("strategy_type must be 'document' or 'file'")
#         self.adapter = adapter
#         self.strategy_type = strategy_type
#
#     def insert(self, *args: Any) -> None:
#         """Insert document or file based on strategy type."""
#         self.adapter.insert(*args)
#
#     def get(self, *args: Any) -> Any:
#         """Get document or file based on strategy type."""
#         return self.adapter.get(*args)
#
#     def update(self, *args: Any) -> None:
#         """Update document or file based on strategy type."""
#         self.adapter.update(*args)
#
#     def delete(self, *args: Any) -> None:
#         """Delete document or file based on strategy type."""
#         self.adapter.delete(*args)
#
#
# if __name__ == "__main__":
#     redis_client = redis.Redis(host='localhost', port=6379, decode_responses=False)
#     redis_adapter = RedisAdapter(redis_client)
#     redis_storage = RedisStorage(redis_adapter)
#
#     redis_storage.set("key1", "value1")
#     redis_storage.update({"key2": "value2", "key3": "value3"})
#     print(f"Redis get key1: {redis_storage.get('key1')}")
#     redis_storage.delete(["key2", "key3"])
#
#     zk_client = KazooClient(hosts='localhost:2181')
#     zk_client.start()
#     zk_adapter = ZookeeperAdapter(zk_client, prefix="/app__save")
#     zk_storage = ZookeeperStorage(zk_adapter)
#
#     zk_storage.set("zk_key1", "zk_value1")
#     zk_storage.update({"zk_key2": "zk_value2", "zk_key3": "zk_value3"})
#     print(f"ZooKeeper get zk_key1: {zk_storage.get('zk_key1')}")
#     zk_storage.delete(["zk_key2", "zk_key3"])
#     zk_client.stop()
#
#     mongo_client = MongoClient('localhost', 27017)
#     mongo_adapter = MongoAdapter(mongo_client, database="testdb")
#
#     doc_storage = MongoStorage(mongo_adapter, strategy_type="document")
#     doc_storage.insert("users", {"name": "Alice", "age": 30})
#     user = doc_storage.get("users", {"name": "Alice"})
#     print(f"MongoDB document: {user}")
#     doc_storage.update("users", {"name": "Alice"}, {"age": 31})
#     doc_storage.delete("users", {"name": "Alice"})
#
#     file_storage = MongoStorage(mongo_adapter, strategy_type="file")
#     file_storage.insert("example.txt", b"Hello World")
#     content = file_storage.get("example.txt")
#     print(f"MongoDB file content: {content}")
#     file_storage.update("example.txt", b"Updated Content")
#     file_storage.delete("example.txt")