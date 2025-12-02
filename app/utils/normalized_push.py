from dataclasses import dataclass
from typing import Optional, List

from app.utils.normalized_commit import NormalizedCommit


@dataclass
class NormalizedPush:
    """
    Normalized representation of a push event across GitHub / Bitbucket / Gitea.
    """
    provider: str  # "github" | "bitbucket" | "gitea"
    repository: str  # e.g. 'owner/repo'
    ref: str  # e.g. 'refs/heads/main'
    before: Optional[str]  # SHA before push, if available
    after: Optional[str]  # SHA after push, if available
    commits: List[NormalizedCommit]

    def get_commits_with_file(self, file_path: str) -> List[NormalizedCommit]:
        """Get all commits where a specific file was changed (added or modified)"""
        return [commit for commit in self.commits if commit.has_file_changed(file_path)]

    def get_commit_hashes_with_file(self, file_path: str) -> List[str]:
        """Get commit hashes where a specific file was changed"""
        return [commit.hash for commit in self.commits if commit.has_file_changed(file_path)]

    def get_first_commit(self) -> Optional[NormalizedCommit]:
        """Get the first commit in the push"""
        return self.commits[0] if self.commits else None

    def get_last_commit(self) -> Optional[NormalizedCommit]:
        """Get the last commit in the push"""
        return self.commits[-1] if self.commits else None