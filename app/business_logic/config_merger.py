import copy
from typing import Dict, Any, List


def smart_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merges 'override' into 'base'.
    - Dictionaries are deep merged.
    - Lists/Scalars in 'override' replace 'base'.
    """
    result = copy.deepcopy(base)

    for key, value in override.items():
        if isinstance(value, dict) and key in result and isinstance(result[key], dict):
            result[key] = smart_merge(result[key], value)
        else:
            result[key] = value

    return result


def resolve_config(global_config: Dict[str, Any], repo_config: Dict[str, Any], presets: List[Dict[str, Any]]) -> Dict[
    str, Any]:
    """
    Resolution Order: Global -> Presets -> Repo
    """
    # 1. Start with Global Config as the base
    final_config = copy.deepcopy(global_config)

    # 2. Apply Presets sequentially
    for preset in presets:
        final_config = smart_merge(final_config, preset)

    # 3. Apply Repository Specific Config (Highest Priority)
    final_config = smart_merge(final_config, repo_config)

    return final_config