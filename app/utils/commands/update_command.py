from typing import Any

from app.utils.interfaces.icommand import ICommand


class UpdateCommand(ICommand):
    """Command to update data using a storage strategy."""

    def __init__(self, strategy: StorageStrategy, *args: Any) -> None:
        self.strategy = strategy
        self.args = args
        self._backup = None

    def execute(self) -> Any:
        """Execute update operation, backing up old data first."""
        # Backup current state for undo
        self._backup_data()
        self.strategy.update(*self.args)
        return None

    def _backup_data(self) -> None:
        """Backup current data before update."""
        # For key-value stores with bulk update
        if isinstance(self.strategy, KeyValueStorageStrategy) and len(self.args) == 1:
            items = self.args[0]
            self._backup = {}
            for key in items.keys():
                self._backup[key] = self.strategy.get(key)
        # For document stores
        elif isinstance(self.strategy, DocumentStorageStrategy) and len(self.args) == 3:
            collection, query, _ = self.args
            self._backup = self.strategy.get(collection, query)
        # For file stores
        elif isinstance(self.strategy, FileStorageStrategy) and len(self.args) == 2:
            path = self.args[0]
            self._backup = self.strategy.get(path)