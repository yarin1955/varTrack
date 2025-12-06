# def flatten_json(data, separator='/'):
#     """
#     Flatten nested JSON to key-value pairs without recursion.
#     Uses ZooKeeper-style path notation with configurable separator.
#
#     Args:
#         data: JSON data (dict, list, or primitive)
#         separator: String to separate nested keys (default: '/')
#
#     Returns:
#         dict: Flattened key-value pairs
#     """
#     if not isinstance(data, (dict, list)):
#         return {'': data}
#
#     result = {}
#     # Stack stores tuples of (current_data, current_path)
#     stack = [(data, '')]
#
#     while stack:
#         current_data, current_path = stack.pop()
#
#         if isinstance(current_data, dict):
#             if not current_data:  # Empty dict
#                 result[current_path] = {}
#             else:
#                 for key, value in current_data.items():
#                     new_path = f"{current_path}{separator}{key}" if current_path else key
#
#                     if isinstance(value, (dict, list)):
#                         stack.append((value, new_path))
#                     else:
#                         result[new_path] = value
#
#         elif isinstance(current_data, list):
#             if not current_data:  # Empty list
#                 result[current_path] = []
#             else:
#                 for index, value in enumerate(current_data):
#                     new_path = f"{current_path}{separator}{index}" if current_path else str(index)
#
#                     if isinstance(value, (dict, list)):
#                         stack.append((value, new_path))
#                     else:
#                         result[new_path] = value
#
#     return result
#
#
# def unflatten_json(flat_data, separator='/'):
#     """
#     Reconstruct nested JSON from flattened key-value pairs.
#
#     Args:
#         flat_data: dict with flattened keys
#         separator: String used to separate nested keys
#
#     Returns:
#         Reconstructed nested structure
#     """
#     if not flat_data:
#         return {}
#
#     result = {}
#
#     for flat_key, value in flat_data.items():
#         if not flat_key:  # Empty key means root value
#             return value
#
#         keys = flat_key.split(separator)
#         current = result
#
#         # Navigate/create the nested structure
#         for i, key in enumerate(keys[:-1]):
#             # Check if key should be treated as array index
#             if key.isdigit():
#                 key = int(key)
#                 # Convert current to list if needed
#                 if not isinstance(current, list):
#                     current = []
#                     if i == 0:
#                         result = current
#
#                 # Extend list if necessary
#                 while len(current) <= key:
#                     current.append(None)
#
#                 # Initialize nested structure
#                 if current[key] is None:
#                     next_key = keys[i + 1]
#                     current[key] = [] if next_key.isdigit() else {}
#
#                 current = current[key]
#             else:
#                 if key not in current:
#                     next_key = keys[i + 1] if i + 1 < len(keys) else None
#                     current[key] = [] if next_key and next_key.isdigit() else {}
#                 current = current[key]
#
#         # Set the final value
#         final_key = keys[-1]
#         if final_key.isdigit() and isinstance(current, list):
#             final_key = int(final_key)
#             while len(current) <= final_key:
#                 current.append(None)
#             current[final_key] = value
#         else:
#             current[final_key] = value
#
#     return result
from collections import deque
from typing import Any, Union, Dict

from typing import Any, Dict, Union


def flatten_dfs(
        data: Any,
        env_key: str = "predev",
        as_kv: bool = False,
        use_default_fallback: bool = False,
        default_key: str = "default_value",  # Note: Updated based on your JSON ("default_value")
        separator: str = "/",
) -> Union[Any, Dict[str, Any]]:
    """Flatten nested data with env overrides using DFS (no recursion limits)."""

    def _esc(s: str) -> str:
        return s.replace("~", "~0").replace("/", "~1")

    def _res(v: Any) -> Any:
        # Check for env_key first
        if isinstance(v, dict) and env_key in v:
            return v[env_key]
        # Check for default_key fallback
        if isinstance(v, dict) and use_default_fallback and default_key in v:
            return v[default_key]
        return v

    # Resolve root
    data = _res(data)

    if not isinstance(data, (dict, list)):
        return {"": data} if as_kv else data

    # Initialize result
    result = {} if as_kv else ([] if isinstance(data, list) else {})

    # Stack contains: (source_node, destination_node, current_path_list)
    stack = [(data, result, [])]

    while stack:
        src, dst, path = stack.pop()

        # Determine iterator based on type
        iterator = src.items() if isinstance(src, dict) else enumerate(src)

        # Reverse to maintain order in stack (DFS)
        for key, raw in reversed(list(iterator)):
            val = _res(raw)
            new_path = path + [_esc(str(key))]

            if isinstance(val, (dict, list)):
                if as_kv:
                    stack.append((val, None, new_path))
                else:
                    new_dst = [] if isinstance(val, list) else {}

                    # --- FIX START ---
                    # Explicitly handle assignment based on parent type (src)
                    if isinstance(src, dict):
                        dst[key] = new_dst
                    else:
                        dst.append(new_dst)
                    # --- FIX END ---

                    stack.append((val, new_dst, new_path))
            else:
                if as_kv:
                    k_str = separator + separator.join(new_path) if new_path else ""
                    result[k_str] = val
                else:
                    # --- FIX START ---
                    if isinstance(src, dict):
                        dst[key] = val
                    else:
                        dst.append(val)
                    # --- FIX END ---

    return result


# def find_key_iterative(obj, target_key, return_value_only=False):
#     """Non-recursive search for a key in nested JSON"""
#     results = []
#     queue = deque([(obj, "")])
#
#     while queue:
#         current_obj, current_path = queue.popleft()
#
#         if isinstance(current_obj, dict):
#             for key, value in current_obj.items():
#                 path = f"{current_path}.{key}" if current_path else key
#
#                 if key == target_key:
#                     results.append({
#                         "path": path,
#                         "value": value
#                     })
#
#                 if isinstance(value, (dict, list)):
#                     queue.append((value, path))
#
#         elif isinstance(current_obj, list):
#             for i, item in enumerate(current_obj):
#                 path = f"{current_path}[{i}]"
#                 if isinstance(item, (dict, list)):
#                     queue.append((item, path))
#
#     if return_value_only and results:
#         return results[0]["value"]
#
#     return results
def find_key_iterative(obj, target_key):
    """Non-recursive search for a key in nested JSON"""
    results = []

    # Queue stores tuples of (current_object, path)
    queue = deque([(obj, "")])

    while queue:
        current_obj, current_path = queue.popleft()

        if isinstance(current_obj, dict):
            for key, value in current_obj.items():
                path = f"{current_path}.{key}" if current_path else key

                # Found the target key
                if key == target_key:
                    results.append({
                        "path": path,
                        "value": value
                    })

                # Add nested structures to queue
                if isinstance(value, (dict, list)):
                    queue.append((value, path))

        elif isinstance(current_obj, list):
            for i, item in enumerate(current_obj):
                path = f"{current_path}[{i}]"

                # Add nested structures to queue
                if isinstance(item, (dict, list)):
                    queue.append((item, path))

    return results[0]
