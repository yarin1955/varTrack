from dataclasses import dataclass
from typing import Optional, List

from app.utils.normalized_commit import NormalizedCommit


@dataclass
class NormalizedPush:
    """Represents a standard Git push event."""
    repository: str  # e.g. 'owner/repo'
    branch: str         # e.g. 'refs/heads/main'
    before: str      # SHA before push
    after: str       # SHA after push
    commits: List[NormalizedCommit]