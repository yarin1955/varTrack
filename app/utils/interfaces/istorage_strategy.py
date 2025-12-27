from abc import abstractmethod, ABC
from typing import Any


class IStorageStrategy(ABC):
    """Abstract base class for update strategies"""

    @staticmethod
    @abstractmethod
    def write(*args: Any, **kwargs: Any) -> None:
        """
        Insert data into storage.
        Accepts generic arguments to allow flexibility in implementation.
        """
        pass