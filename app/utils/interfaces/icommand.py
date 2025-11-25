from abc import ABC, abstractmethod
from typing import Any


class Command(ABC):
    """Base command interface."""

    @abstractmethod
    def execute(self) -> Any:
        """Execute the command."""
        pass

    @abstractmethod
    def undo(self) -> None:
        """Undo the command (optional implementation)."""
        pass