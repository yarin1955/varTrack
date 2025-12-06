from dataclasses import dataclass, field
from typing import List
from app.utils.normalized_commit import NormalizedCommit

@dataclass
class NormalizedPR:
    """Represents a Pull Request event."""
    id: str
    action: str  # e.g., 'opened', 'synchronize', 'closed'
    repository: str  # e.g. 'owner/repo'
    base_branch: str  # Target branch (e.g., 'main')
    head_branch: str  # Source branch (e.g., 'feature-1')

    base_sha: str  # SHA of the merge base (ancestor) used for comparison
    target_branch_sha: str  # SHA of the actual tip of base_ref

    head_sha: str  # SHA of the head branch (after)
    is_approved: bool
    commits: List[NormalizedCommit] = field(default_factory=list)