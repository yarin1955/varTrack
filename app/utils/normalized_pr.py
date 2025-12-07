from dataclasses import dataclass, field
from typing import List, Set
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

    def sort_commits(self, reverse: bool = True) -> None:
        """
        Args: reverse: If True, sort newest to oldest. Default False (oldest to newest).
        """
        self.commits.sort(
            key=lambda c: c.timestamp.timestamp() if c.timestamp else 0.0,
            reverse=reverse
        )

    def get_all_changed_files(self) -> Set[str]:
        all_files = set()
        for commit in self.commits:
            # Uses the method we created in the previous step
            all_files.update(commit.get_changed_files())

        return all_files