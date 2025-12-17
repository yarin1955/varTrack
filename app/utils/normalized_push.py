from dataclasses import dataclass
from typing import Optional, List, Set, Dict

from app.utils.normalized_commit import NormalizedCommit, FileChange
import re

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
        """Get unique set of all files changed across all commits."""
        return {file_path for commit in self.commits for file_path in commit.get_changed_files()}

    def get_changes_by_filename(self, filename: str) -> List[FileChange]:

        matches = []
        for commit in self.commits:
            for file_change in commit.files:
                if file_change.path == filename:
                    matches.append(file_change)
        return matches

    def get_changes_by_path_map(self, file_path_map: Dict[str, str]) -> List[FileChange]:

        if not file_path_map:
            return []

        combined_pattern = "|".join(f"(?:{p})" for p in file_path_map.keys())
        master_regex = re.compile(combined_pattern)
        matches = []

        # 2. Single pass filtering
        for commit in self.commits:
            for file_change in commit.files:
                # One check per file, regardless of how many patterns exist
                if master_regex.match(file_change.path):
                    matches.append(file_change)

        return matches

    def get_matching_files(self, filename: Optional[str] = None, file_path_map: Optional[Dict[str, str]] = None) -> List[FileChange]:

        if filename:
            return self.get_changes_by_filename(filename)
        elif file_path_map:
            return self.get_changes_by_path_map(file_path_map)
        return []