from dataclasses import dataclass, field
from datetime import datetime
from typing import List


@dataclass
class NormalizedCommit:
    """
    A single commit in a push, in a provider-agnostic format.
    """
    hash: str
    added: List[str] = field(default_factory=list)
    modified: List[str] = field(default_factory=list)
    removed: List[str] = field(default_factory=list)
    timestamp: datetime | None = None

    def has_file_changed(self, file_path: str) -> bool:
        """Check if a specific file was changed (added or modified)"""
        return file_path in self.added or file_path in self.modified

    def has_file_added(self, file_path: str) -> bool:
        """Check if a specific file was added"""
        return file_path in self.added