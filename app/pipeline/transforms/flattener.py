from typing import Dict, Any
from app.pipeline.transform import Transform
from app.business_logic.json_pathmap import flatten_dfs, find_key_iterative


class Flattenizer(Transform):
    def __init__(self, root_key: str = "varTrack"):
        self.root_key = root_key

    def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if not data:
            return {}

        target_node_wrapper = find_key_iterative(data, self.root_key)
        target_node = target_node_wrapper.get('value') if target_node_wrapper else None

        if target_node:
            # FIX: as_kv=False keeps it as a nested Dictionary (Standard JSON)
            return flatten_dfs(target_node, as_kv=False)

        return {}