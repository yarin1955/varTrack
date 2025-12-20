from abc import ABC, abstractmethod
from typing import List, Any
from app.pipeline.models import PipelineRow

class Transform(ABC):
    @abstractmethod
    def process(self, *args, **kwargs) -> Any:
        """
        Processes data. Input/Output depends on the specific transform step.
        """
        pass