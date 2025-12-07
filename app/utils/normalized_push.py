from dataclasses import dataclass
from typing import Optional, List, Set

from app.utils.normalized_commit import NormalizedCommit


@dataclass
class NormalizedPush:
    """Represents a standard Git push event."""
    repository: str  # e.g. 'owner/repo'
    branch: str         # e.g. 'refs/heads/main'
    before: str      # SHA before push
    after: str       # SHA after push
    commits: List[NormalizedCommit]

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