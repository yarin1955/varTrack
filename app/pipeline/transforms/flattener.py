from typing import Dict, Any
from app.pipeline.transform import Transform
from app.business_logic.json_pathmap import flatten_dfs, find_key_iterative


class Flattenizer(Transform):
    """
    Flattens a specific section of the configuration (e.g. 'varTrack').
    """

    def __init__(self, root_key: str = "varTrack"):
        self.root_key = root_key

    def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if not data:
            return {}

        # 1. Find the target root node (e.g. key "varTrack")
        # find_key_iterative returns {'value': ...} or None depending on your impl.
        # Assuming your updated find_key_iterative returns the node or None.
        target_node_wrapper = find_key_iterative(data, self.root_key)

        # Adjust based on your find_key_iterative implementation returning a dict or val
        target_node = target_node_wrapper.get('value') if target_node_wrapper else None

        if target_node:
            # 2. Flatten it
            return flatten_dfs(target_node)

        return {}