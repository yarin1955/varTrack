from dataclasses import dataclass, field
from typing import List
from app.utils.normalized_commit import NormalizedCommit

@dataclass
class NormalizedPR:
    """Represents a Pull Request event."""
    id: str
    repository: str   # e.g. 'owner/repo'
    base_ref: str     # Target branch (e.g., 'main')
    head_ref: str     # Source branch (e.g., 'feature-1')
    base_sha: str     # SHA of the base branch (before)
    head_sha: str     # SHA of the head branch (after)
    is_approved: bool
    commits: List[NormalizedCommit] = field(default_factory=list)