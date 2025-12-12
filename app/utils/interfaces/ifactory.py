import importlib
from types import ModuleType
from typing import Union, Optional, Type, TypeVar
import importlib.util
import sys
from abc import ABC, abstractmethod
from pathlib import Path

from app.utils.class_loader import load_class_from_package_module

T = TypeVar('T')
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
    def load_module(cls, name: str):
        pass

    @staticmethod
    def _load_class_from_package_module(module_name: str, package_module: ModuleType, expected_base_class: Optional[Type[T]] = None) -> Type[T]:

        return load_class_from_package_module(module_name, package_module,expected_base_class)

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
    def create(cls, *args, **kwargs):
        name = kwargs.get("name")
        if not name:
            raise ValueError(f"{cls.__name__}.create() requires a 'name' argument.")
        try:
            plugin_cls = cls._registry[name]
        except KeyError:
            cls.load_module(name)

            plugin_cls = cls._registry.get(name)

            if not plugin_cls:
                raise ValueError(
                    f"No class registered as '{name}'. "
                    f"Ensure the module exists and the class is decorated with @{cls.__name__}.register()."
                )
        return plugin_cls(*args, **kwargs)
