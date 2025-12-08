from abc import ABC, abstractmethod
from typing import Any


class IStorageStrategy(ABC):
    """Abstract base class for update strategies"""

    @abstractmethod
    def insert(self, *args: Any, **kwargs: Any) -> None:
        """Insert data into storage."""
        pass

    @abstractmethod
    def upsert(self, *args: Any, **kwargs: Any) -> None:
        """Insert data into storage."""
        pass

    @abstractmethod
    def get(self, *args: Any, **kwargs: Any) -> Any:
        """Retrieve data from storage."""
        pass

    @abstractmethod
    def update(self, *args: Any, **kwargs: Any) -> None:
        """Update data in storage."""
        pass

    @abstractmethod
    def delete(self, *args: Any, **kwargs: Any) -> None:
        """Delete data from storage."""
        pass