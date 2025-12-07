from typing import Any
from app.models.ds_adapter import DataSourceAdapter
from app.utils.interfaces.icommand import ICommand


class InsertCommand(ICommand):
    """Command to insert data using a storage strategy."""

    def __init__(self, ds_adapter: DataSourceAdapter, data) -> None:
        self.ds_adapter = ds_adapter
        self.data = data
        self._backup = None

    def execute(self) -> Any:
        """Execute insert operation."""
        self.ds_adapter.insert(self.data)
        return None