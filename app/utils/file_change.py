from dataclasses import dataclass, field
from typing import Optional, List, Dict


@dataclass
class ChangeFile:
    """Represents a processed file change destined for VarTrack."""
    file_path: str
    env: str
    key: str
    before_sha: str
    after_sha: str
    variables: Dict[str, str] = field(default_factory=dict)

    # def add_commit(self, commit_hash: str):
    #     """Add a commit hash, maintaining first and last"""
    #     self.all_commits.append(commit_hash)
    #     if self.first_commit is None:
    #         self.first_commit = commit_hash
    #     self.last_commit = commit_hash