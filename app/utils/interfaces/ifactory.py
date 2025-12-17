from abc import ABC
from typing import Dict, Type, List, Optional
from types import ModuleType


class IFactory(ABC):
    # Registry to hold subclass references
    _registry: Dict[str, Type] = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        # 1. Reset registry if this is a Base Class (like GitPlatform)
        if IFactory in cls.__bases__:
            cls._registry = {}
            return

        # 2. Skip abstract helpers
        if ABC in cls.__bases__:
            return

        # 3. Register the Child Class (Plugin)
        # Key = filename (e.g., 'app.models.git_platforms.github' -> 'github')
        key = cls.__module__.rsplit('.', 1)[-1]

        # Optional: Check for duplicates
        if key in cls._registry and cls._registry[key] != cls:
            print(f"Warning: Overwriting registry key '{key}' with {cls.__name__}")

        cls._registry[key] = cls

    @classmethod
    def create(cls, *args, **kwargs):
        name = kwargs.get("name")

        # 1. Lazy Load Module if needed
        if name not in cls._registry:
            try:
                cls.load_module(name)
            except Exception as e:
                print(f"[Factory] Warning: Could not load module '{name}': {e}")

        # 2. Get the specific class (e.g. GitHubSettings)
        target_cls = cls._registry.get(name)
        if not target_cls:
            # Fallback or Error
            available = list(cls._registry.keys())
            raise ValueError(f"Class '{name}' not found in registry. Available: {available}")

        # 3. Instantiate WITH 'name' explicitly passed back
        # This fixes the "missing name property" issue
        return target_cls(*args, **kwargs)

    @classmethod
    def load_module(cls, name: str):
        """
        Override this in the base class (e.g., GitPlatform) to define
        where to look for plugins/subclasses.
        """
        pass

    @classmethod
    def get_registry_keys(cls) -> List[str]:
        """
        Returns a list of all currently registered keys.
        Useful for debugging or creating dynamic choices in a UI/CLI.
        """
        return list(cls._registry.keys())

    @staticmethod
    def _load_class_from_package_module(module_name: str, package_module: ModuleType) -> None:
        """
        Internal helper to delegate to the utility function.
        Keeps the interface clean if you want to call it from subclasses.
        """
        # Assuming you have the utility we wrote in app/utils/class_loader.py
        from app.utils.class_loader import load_class_from_package_module
        load_class_from_package_module(module_name, package_module)