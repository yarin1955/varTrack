from abc import ABC, abstractmethod
from typing import Any

class ICommand(ABC):

    @abstractmethod
    def execute(self, *args: Any, **kwargs: Any) -> Any:
        pass
