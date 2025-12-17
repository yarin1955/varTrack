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

# import importlib
# import inspect
# from types import ModuleType
# from typing import Type, TypeVar, Optional
#
# T = TypeVar('T')
#
# def load_class_from_package_module(
#         module_name: str,
#         package_module: ModuleType,
#         expected_base_class: Optional[Type[T]] = None
# ) -> Type[T]:
#     """
#     Loads a class from a module, using a Module object to determine location.
#     """
#     # 1. Extract the string path from the module object automatically
#     package_path = package_module.__name__  # e.g. "app.models.git_platforms"
#     full_import_path = f"{package_path}.{module_name}"
#
#     try:
#         # Import relative to the package path derived from the module
#         mod = importlib.import_module(f".{module_name}", package=package_path)
#     except ImportError as e:
#         raise ImportError(
#             f"Plugin not found. Expected at: {full_import_path}"
#         ) from e
#
#     # Find candidate classes
#     candidates = [
#         obj for obj in mod.__dict__.values()
#         if inspect.isclass(obj) and obj.__module__ == mod.__name__
#     ]
#
#     if expected_base_class:
#         candidates = [
#             cls for cls in candidates
#             if issubclass(cls, expected_base_class) and cls is not expected_base_class
#         ]
#         if not candidates:
#             raise ValueError(f"No class inheriting from '{expected_base_class.__name__}' found in '{full_import_path}'")
#         if len(candidates) > 1:
#             raise ValueError(f"Ambiguous plugin: Found {len(candidates)} classes in '{full_import_path}'")
#     else:
#         if len(candidates) != 1:
#             raise ValueError(f"Expected exactly one class in '{full_import_path}', found {len(candidates)}")
#
#     return candidates[0]