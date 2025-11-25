from abc import abstractmethod

from app__save.util.interfaces.istorage_strategy import IStorageStrategy

class KeyValueStorageStrategy(IStorageStrategy):
    """Strategy for key-value storage operations."""

    def insert(self, key: str, value: str) -> None:
        """Insert or set a key-value pair."""
        pass

    def get(self, key: str) -> str | None:
        """Get value by key, returns None if not found."""
        pass

    def update(self, items: dict[str, str]) -> None:
        """Bulk update multiple key-value pairs. Creates keys if missing."""
        pass

    def delete(self, keys: list[str]) -> None:
        """Bulk delete multiple keys. Ignores missing keys."""
        pass