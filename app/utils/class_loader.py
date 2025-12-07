import importlib
import inspect
from typing import Type, TypeVar, Optional

T = TypeVar('T')

def load_class_from_module(
        module_name: str,
        package: str,
        expected_base_class: Optional[Type[T]] = None
) -> Type[T]:

    full_path = f"{package}.{module_name}"

    try:
        mod = importlib.import_module(f".{module_name}", package=package)
    except ImportError as e:
        raise ImportError(
            f"Plugin not found. Expected file at: {full_path.replace('.', '/')}.py"
        ) from e

    # Find candidate classes defined in this module
    candidates = [
        obj for obj in mod.__dict__.values()
        if inspect.isclass(obj) and obj.__module__ == mod.__name__
    ]

    # Apply base class filter if specified
    if expected_base_class:
        candidates = [
            cls for cls in candidates
            if issubclass(cls, expected_base_class) and cls is not expected_base_class
        ]

        if not candidates:
            raise ValueError(
                f"No class inheriting from '{expected_base_class.__name__}' "
                f"found in module '{full_path}'."
            )

        if len(candidates) > 1:
            raise ValueError(
                f"Ambiguous plugin: Found {len(candidates)} classes inheriting from "
                f"'{expected_base_class.__name__}' in '{full_path}': {candidates}"
            )
    else:
        # No base class specified - expect exactly one class
        if len(candidates) != 1:
            raise ValueError(
                f"Expected exactly one class in module '{full_path}', found {len(candidates)}"
            )

    return candidates[0]