
from kazoo.client import KazooClient

from app.models.ds_adapter import DataSourceAdapter

class ZookeeperAdapter(DataSourceAdapter):
    """Adapter for ZooKeeper backend implementing key-value operations."""

    def __init__(self, client: KazooClient, prefix: str = "/app__save") -> None:
        """Initialize with KazooClient and path prefix."""
        self.client = client
        self.prefix = prefix

    def _get_path(self, key: str) -> str:
        """Convert key to ZooKeeper path."""
        return f"{self.prefix}/{key}"

    def insert(self, key: str, value: str) -> None:
        """Create znode with data. Overwrites if exists."""
        path = self._get_path(key)
        if self.client.exists(path):
            self.client.set(path, value.encode('utf-8'))
        else:
            self.client.create(path, value.encode('utf-8'), makepath=True)

    def get(self, key: str) -> str | None:
        """Get znode data as string, returns None if not found."""
        path = self._get_path(key)
        if self.client.exists(path):
            data, _ = self.client.get(path)
            return data.decode('utf-8')
        return None

    def update(self, items: dict[str, str]) -> None:
        """Bulk update using Kazoo transaction. Creates nodes if missing."""
        if not items:
            return

        transaction = self.client.transaction()
        for key, value in items.items():
            path = self._get_path(key)
            if self.client.exists(path):
                transaction.set_data(path, value.encode('utf-8'))
            else:
                transaction.create(path, value.encode('utf-8'), makepath=True)
        transaction.commit()

    def delete(self, keys: list[str]) -> None:
        """Bulk delete using Kazoo transaction. Ignores missing keys."""
        if not keys:
            return

        transaction = self.client.transaction()
        for key in keys:
            path = self._get_path(key)
            if self.client.exists(path):
                transaction.delete(path)
        transaction.commit()