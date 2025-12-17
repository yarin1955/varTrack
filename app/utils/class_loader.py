import importlib
from types import ModuleType
from typing import Optional, Type, TypeVar

T = TypeVar("T")


def load_class_from_package_module(
        module_name: str,
        package_module: ModuleType,
        expected_base_class: Optional[Type[T]] = None
) -> None:
    try:
        # Construct full path: 'app.models.git_platforms.github'
        full_module_path = f"{package_module.__name__}.{module_name}"

        # This executes the code in the file, triggering __init_subclass__
        importlib.import_module(full_module_path)

    except ImportError as e:
        raise ImportError(f"Could not import module '{full_module_path}'. Reason: {e}")
