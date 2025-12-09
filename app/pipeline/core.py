from abc import ABC, abstractmethod
from typing import List, Any
from app.pipeline.models import PipelineRow

class Source(ABC):
    @abstractmethod
    async def read(self) -> List[Any]:
        """
        Reads data from the external system (Git).
        Returns a list of raw items (e.g., tuples of content) to be processed.
        """
        pass

class Transform(ABC):
    @abstractmethod
    def process(self, *args, **kwargs) -> Any:
        """
        Processes data. Input/Output depends on the specific transform step.
        """
        pass

class Sink(ABC):
    @abstractmethod
    def write(self, row: PipelineRow) -> None:
        """
        Accepts a single row and adds it to the internal buffer.
        """
        pass

    @abstractmethod
    def flush(self) -> None:
        """
        Forces the buffer to be written to the destination system.
        """
        pass