from collections import deque

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

def find_key_iterative(obj, target_key):
    """Non-recursive search for a key in nested JSON"""
    results = []
    queue = deque([(obj, "")])

    while queue:
        current_obj, current_path = queue.popleft()

        if isinstance(current_obj, dict):
            for key, value in current_obj.items():
                path = f"{current_path}.{key}" if current_path else key

                if key == target_key:
                    results.append({
                        "path": path,
                        "value": value
                    })

                if isinstance(value, (dict, list)):
                    queue.append((value, path))

        elif isinstance(current_obj, list):
            for i, item in enumerate(current_obj):
                path = f"{current_path}[{i}]"
                if isinstance(item, (dict, list)):
                    queue.append((item, path))

    # FIX: Safety check to return None if key not found
    return results[0] if results else None