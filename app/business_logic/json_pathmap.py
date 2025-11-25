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


def flatten_dfs(
        data: Any,
        env_key: str = "predev",
        as_kv: bool = False,
        use_default_fallback: bool = False,
        default_key: str = "default",
        separator: str = "/",
) -> Union[Any, Dict[str, Any]]:
    """Flatten nested data with env overrides using DFS (no recursion limits)."""

    def _esc(s: str) -> str:
        return s.replace("~", "~0").replace("/", "~1")

    def _res(v: Any) -> Any:
        return v.get(env_key) if isinstance(v, dict) and env_key in v else \
            v.get(default_key) if isinstance(v, dict) and use_default_fallback and default_key in v else v

    data = _res(data)
    if not isinstance(data, (dict, list)):
        return {"": data} if as_kv else data

    result = {} if as_kv else ([] if isinstance(data, list) else {})
    stack = [(data, result, [])]

    while stack:
        src, dst, path = stack.pop()
        for key, raw in reversed(list(src.items() if isinstance(src, dict) else enumerate(src))):
            val = _res(raw)
            new_path = path + [_esc(str(key))]

            if isinstance(val, (dict, list)):
                if as_kv:
                    stack.append((val, None, new_path))
                else:
                    new_dst = [] if isinstance(val, list) else {}
                    (dst.__setitem__ if isinstance(src, dict) else dst.append)(
                        key if isinstance(src, dict) else new_dst
                    )
                    stack.append((val, new_dst, new_path))
            else:
                if as_kv:
                    result[separator + separator.join(new_path) if new_path else ""] = val
                else:
                    (dst.__setitem__ if isinstance(src, dict) else dst.append)(
                        key if isinstance(src, dict) else val
                    )

    return result


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

    return results
#
#
# def unflatten_dfs(
#         data: Dict[str, Any],
#         separator: str = "/",
#         *,
#         force_list_indices: bool = False,
# ) -> Any:
#     """Reconstruct nested structure from flattened key-value pairs using DFS.
#
#     Args:
#         data: Flattened dict with separator-delimited keys
#         separator: Character used to separate path segments (default: "/")
#         force_list_indices: If True, numeric keys create lists; if False, auto-detect
#
#     Examples:
#         >>> unflatten_dfs({'/db/host': 'localhost', '/db/port': 5432})
#         {'db': {'host': 'localhost', 'port': 5432}}
#
#         >>> unflatten_dfs({'db.host': 'localhost'}, separator='.')
#         {'db': {'host': 'localhost'}}
#
#         >>> unflatten_dfs({'/items/0': 'a', '/items/1': 'b'})
#         {'items': ['a', 'b']}
#     """
#
#     def _unesc(s: str) -> str:
#         return s.replace("~1", "/").replace("~0", "~")
#
#     def _is_int(s: str) -> bool:
#         try:
#             int(s)
#             return True
#         except ValueError:
#             return False
#
#     if not data:
#         return {}
#
#     # Handle empty string key (root scalar)
#     if "" in data and len(data) == 1:
#         return data[""]
#
#     # Determine if root should be list or dict
#     root = None
#
#     for key, val in data.items():
#         # Parse path: strip leading separator, split, unescape
#         path = [_unesc(p) for p in key.lstrip(separator).split(separator) if p]
#
#         if not path:
#             return val  # Root scalar
#
#         # Initialize root on first iteration
#         if root is None:
#             root = [] if (force_list_indices or _is_int(path[0])) else {}
#
#         # Navigate/create path
#         current = root
#         for i, segment in enumerate(path[:-1]):
#             next_segment = path[i + 1]
#             is_next_list = force_list_indices or _is_int(next_segment)
#
#             if isinstance(current, dict):
#                 if segment not in current:
#                     current[segment] = [] if is_next_list else {}
#                 current = current[segment]
#             else:  # list
#                 idx = int(segment)
#                 # Extend list if needed
#                 while len(current) <= idx:
#                     current.append(None)
#                 if current[idx] is None:
#                     current[idx] = [] if is_next_list else {}
#                 current = current[idx]
#
#         # Set final value
#         final_key = path[-1]
#         if isinstance(current, dict):
#             current[final_key] = val
#         else:  # list
#             idx = int(final_key)
#             while len(current) <= idx:
#                 current.append(None)
#             current[idx] = val
#
#     return root