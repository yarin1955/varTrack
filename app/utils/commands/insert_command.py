from typing import Any
from app.models.ds_adapter import DataSourceAdapter
from app.utils.interfaces.icommand import Command


class InsertCommand(Command):
    """Command to insert data using a storage strategy."""

    def __init__(self, ds_adapter: DataSourceAdapter, *args: Any) -> None:
        self.ds_adapter = ds_adapter
        self.args = args
        self._backup = None

    def execute(self) -> Any:
        """Execute insert operation."""
        self.ds_adapter.insert(*self.args)
        return None

    def undo(self) -> None:
        self.ds_adapter.delete(*self.args)
        # For key-value stores
        # if isinstance(self.strategy, KeyValueStorageStrategy) and len(self.args) == 2:
        #     key = self.args[0]
        #     self.strategy.delete([key])
        # # For document stores
        # elif isinstance(self.strategy, DocumentStorageStrategy) and len(self.args) == 2:
        #     collection, document = self.args
        #     if '_id' in document:
        #         self.strategy.delete(collection, {'_id': document['_id']})
        # # For file stores
        # elif isinstance(self.strategy, FileStorageStrategy) and len(self.args) == 2:
        #     path = self.args[0]
        #     self.strategy.delete(path)