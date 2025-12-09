# app/utils/preset_resolver.py
import json
import re
from typing import List, Dict, Any, Optional
from app.models.git_platform import GitPlatform


class PresetResolver:
    """
    Resolves 'extends': ['github>owner/repo:presetName'] into actual config dicts.
    """

    # Regex to parse: source>owner/repo:file
    # Example: github>yarin1955/vartrack-presets:python
    PRESET_REGEX = re.compile(r"^(?P<source>[^>]+)>(?P<repo>[^:]+)(?::(?P<file>.+))?$")

    def __init__(self, platform_instance: GitPlatform):
        self.platform = platform_instance

    async def fetch_preset(self, preset_str: str) -> Dict[str, Any]:
        match = self.PRESET_REGEX.match(preset_str)
        if not match:
            print(f"⚠️ Invalid preset format: {preset_str}")
            return {}

        source = match.group("source")
        repo = match.group("repo")
        filename = match.group("file") or "default"

        # Normalize filename (append .json if missing)
        if not filename.endswith(".json"):
            filename += ".json"

        # Currently only supporting same-platform presets for simplicity
        # Real Renovate supports cross-platform (e.g. GitLab fetching from GitHub)
        if source != self.platform.name:
            print(f"⚠️ Cross-platform presets not yet supported: {source} != {self.platform.name}")
            return {}

        print(f"📥 Fetching preset '{filename}' from {repo}...")

        # Use a generic 'main' or 'master' branch for presets usually
        # Optimally, we should allow specifying tag like :file#v1.0.0
        # For now, fetching from HEAD (default branch logic required in get_file usually)
        # We'll try fetching from 'main' or 'master' if platform requires branch
        # Assuming get_file_from_commit can take a branch name

        content = await self.platform.get_file_from_commit(repo, "main", filename)
        if not content:
            content = await self.platform.get_file_from_commit(repo, "master", filename)

        if content:
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                print(f"❌ Error decoding JSON from preset {preset_str}")

        return {}

    async def resolve_all(self, extends_list: List[str]) -> List[Dict[str, Any]]:
        resolved_presets = []
        for preset_str in extends_list:
            config = await self.fetch_preset(preset_str)
            if config:
                resolved_presets.append(config)
        return resolved_presets