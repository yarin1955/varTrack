from abc import abstractmethod

from app.utils.interfaces.istorage_strategy import IStorageStrategy


class DocumentStorageStrategy(IStorageStrategy):
    """Strategy for document-oriented storage operations."""

    def insert(self, collection: str, document: dict) -> None:
        """Insert a document into a collection."""
        pass

    def get(self, collection: str, query: dict) -> dict | None:
        """Retrieve a document matching the query."""
        pass

    def update(self, collection: str, query: dict, update: dict) -> None:
        """Update a document matching the query."""
        pass

    def delete(self, collection: str, query: dict) -> None:
        """Delete document(s) matching the query."""
        pass