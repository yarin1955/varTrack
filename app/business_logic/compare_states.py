import json
from typing import Union, Any, Dict


def compare_states(
        current_data: Union[str, Any],
        old_data: Union[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """
    Compare two data structures and return deleted, added, and changed items.

    Args:
        current_data: The current/new data structure (can be JSON string or dict/list)
        old_data: The old/previous data structure (can be JSON string or dict/list)

    Returns:
        Dictionary with 'deleted', 'added', and 'changed' keys containing the differences
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

    # Handle non-dict cases
    if not isinstance(current_data, dict):
        current_data = {'': current_data} if current_data is not None else {}
    if not isinstance(old_data, dict):
        old_data = {'': old_data} if old_data is not None else {}

    # Find deleted keys (in old but not in current)
    for key in old_data:
        if key not in current_data:
            deleted[key] = old_data[key]

    # Find added keys (in current but not in old)
    for key in current_data:
        if key not in old_data:
            added[key] = current_data[key]

    # Find changed keys (in both but with different values)
    for key in current_data:
        if key in old_data and current_data[key] != old_data[key]:
            changed[key] = {
                'old': old_data[key],
                'new': current_data[key]
            }

    return {
        'deleted': deleted,
        'added': added,
        'changed': changed
    }
# def compare_json_strings(json_str1, json_str2, separator='/'):
#     """
#     Compare two JSON strings and return what was deleted, added, and changed.
#     Uses flattened path notation for structured comparison.
#
#     Args:
#         json_str1: First JSON string (original)
#         json_str2: Second JSON string (new/modified)
#         separator: String to separate nested keys (default: '/')
#
#     Returns:
#         dict: Dictionary with 'deleted', 'added', and 'changed' keys containing the differences
#     """
#     try:
#         data1 = json.loads(json_str1) if json_str1 else {}
#         data2 = json.loads(json_str2) if json_str2 else {}
#     except json.JSONDecodeError as e:
#         raise ValueError(f"Invalid JSON string: {e}")
#
#     # Flatten both JSON structures
#     # flat1 = flatten_json(data1, separator)
#     # flat2 = flatten_json(data2, separator)
#
#     # Get all unique keys from both flattened dictionaries
#     keys1 = set(flat1.keys())
#     keys2 = set(flat2.keys())
#
#     # Find differences
#     deleted = {}
#     added = {}
#     changed = {}
#
#     # Keys that exist in original but not in new (deleted)
#     for key in keys1 - keys2:
#         deleted[key] = flat1[key]
#
#     # Keys that exist in new but not in original (added)
#     for key in keys2 - keys1:
#         added[key] = flat2[key]
#
#     # Keys that exist in both but have different values (changed)
#     for key in keys1 & keys2:
#         if flat1[key] != flat2[key]:
#             changed[key] = {
#                 'old': flat1[key],
#                 'new': flat2[key]
#             }
#
#     return {
#         'deleted': deleted,
#         'added': added,
#         'changed': changed
#     }