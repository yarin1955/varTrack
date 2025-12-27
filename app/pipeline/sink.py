from abc import abstractmethod

from app.models.datasource import DataSource
from app.pipeline.pipeline_row import PipelineRow
from app.utils.interfaces.ifactory import IFactory


class Sink(IFactory):

    @classmethod
    def load_module(cls, name: str):
        from app.pipeline import sinks

        cls._load_class_from_package_module(
            module_name=name,
            package_module=sinks
        )

    @classmethod
    def create(cls, *args, **kwargs):
        ds_instance = DataSource.create(*args, **kwargs)
        name = kwargs.get("name")

        if name not in cls._registry:
            cls.load_module(name)

        target_cls = cls._registry.get(name)
        if not target_cls:
            raise ValueError(f"Source class '{name}' not found. Available: {list(cls._registry.keys())}")

        return target_cls(ds_instance)

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