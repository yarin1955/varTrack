import json
from typing import Union, Any, Dict

def compare_states(
        current_data: Union[str, Any],
        old_data: Union[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """
    Compare two data structures and return deleted, added, changed, and unchanged items.

    Args:
        current_data: The current/new data structure (can be JSON string or dict/list)
        old_data: The old/previous data structure (can be JSON string or dict/list)

    Returns:
        Dictionary with 'deleted', 'added', 'changed', and 'unchanged' keys.
    """
    # Parse JSON strings if needed
    if isinstance(current_data, str):
        try:
            current_data = json.loads(current_data)
        except json.JSONDecodeError:
            current_data = {}

    if isinstance(old_data, str):
        try:
            old_data = json.loads(old_data)
        except json.JSONDecodeError:
            old_data = {}

    deleted = {}
    added = {}
    changed = {}
    unchanged = {}

    # Handle non-dict cases
    if not isinstance(current_data, dict):
        current_data = {'': current_data} if current_data is not None else {}
    if not isinstance(old_data, dict):
        old_data = {'': old_data} if old_data is not None else {}

    # Find deleted keys (in old but not in current)
    for key in old_data:
        if key not in current_data:
            deleted[key] = old_data[key]

    # Find added, changed, and unchanged keys
    for key in current_data:
        if key not in old_data:
            added[key] = current_data[key]
        elif current_data[key] != old_data[key]:
            # Changed: store only the new value, not {'old': ..., 'new': ...}
            changed[key] = current_data[key]
        else:
            # Unchanged: value is the same in both
            unchanged[key] = current_data[key]

    return {
        'deleted': deleted,
        'added': added,
        'changed': changed,
        'unchanged': unchanged
    }
