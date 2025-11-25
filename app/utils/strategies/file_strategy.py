from abc import abstractmethod

from app.utils.interfaces.istorage_strategy import IStorageStrategy


class FileStorageStrategy(IStorageStrategy):

    def insert(self, path: str, content: bytes) -> None:
        """Insert file content at path."""
        pass

    def get(self, path: str) -> bytes | None:
        """Retrieve file content by path."""
        pass

    def update(self, path: str, content: bytes) -> None:
        """Update file content at path."""
        pass

    def delete(self, path: str) -> None:
        """Delete file at path."""
        pass