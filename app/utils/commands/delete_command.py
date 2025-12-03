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