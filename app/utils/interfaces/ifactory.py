import importlib
from typing import Union
import importlib.util
import sys
from abc import ABC, abstractmethod
from pathlib import Path
class IFactory(ABC):

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._registry: dict[str, type] = {}

    @classmethod
    @abstractmethod
    def register(cls):
        def decorator(chosen_cls: type) -> type:
            name = chosen_cls.__module__.rsplit('.', 1)[-1]
            # Check for duplicates (optional but often helpful)
            if name in cls._registry:
                existing = cls._registry[name]
                raise KeyError(f"Class name '{name}' is already registered to {existing}.")
            # Register the class under the given name
            cls._registry[name] = chosen_cls
            return chosen_cls

        return decorator


    @classmethod
    @abstractmethod
    def get_registry(cls) -> dict[str, type]:
        """Return the registry mapping names to classes."""
        return dict(cls._registry)

    @classmethod
    @abstractmethod
    def get_registry_keys(cls):
        """Return the registry mapping names to classes."""
        return dict(cls._registry).keys()

    @classmethod
    @abstractmethod
    def create(cls, *args, **kwargs):
        name = kwargs.get("name")
        if name not in cls._registry:
            raise ValueError(f"No data source registered as '{name}'")
        return cls._registry[name](*args, **kwargs)
