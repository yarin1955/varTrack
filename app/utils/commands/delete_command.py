class DeleteCommand(Command):
    """Command to delete data using a storage strategy."""

    def __init__(self, strategy: StorageStrategy, *args: Any) -> None:
        self.strategy = strategy
        self.args = args
        self._backup = None

    def execute(self) -> Any:
        """Execute delete operation, backing up data first."""
        # Backup current state for undo
        self._backup_data()
        self.strategy.delete(*self.args)
        return None

    def _backup_data(self) -> None:
        """Backup data before deletion."""
        # For key-value stores with bulk delete
        if isinstance(self.strategy, KeyValueStorageStrategy) and len(self.args) == 1:
            keys = self.args[0]
            self._backup = {}
            for key in keys:
                self._backup[key] = self.strategy.get(key)
        # For document stores
        elif isinstance(self.strategy, DocumentStorageStrategy) and len(self.args) == 2:
            collection, query = self.args
            self._backup = self.strategy.get(collection, query)
        # For file stores
        elif isinstance(self.strategy, FileStorageStrategy) and len(self.args) == 1:
            path = self.args[0]
            self._backup = self.strategy.get(path)

    def undo(self) -> None:
        """Restore deleted data."""
        if self._backup is None:
            return

        # For key-value stores
        if isinstance(self.strategy, KeyValueStorageStrategy) and isinstance(self._backup, dict):
            # Filter out None values (keys that didn't exist)
            restore_items = {k: v for k, v in self._backup.items() if v is not None}
            if restore_items:
                for key, value in restore_items.items():
                    self.strategy.insert(key, value)
        # For document stores
        elif isinstance(self.strategy, DocumentStorageStrategy) and len(self.args) == 2:
            collection = self.args[0]
            if self._backup:
                self.strategy.insert(collection, self._backup)
        # For file stores
        elif isinstance(self.strategy, FileStorageStrategy) and len(self.args) == 1:
            path = self.args[0]
            if self._backup:
                self.strategy.insert(path, self._backup)