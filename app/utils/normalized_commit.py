from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Set

from app.utils.enums.file_status import FileStatus


@dataclass(frozen=True)
class FileChange:
    path: str
    status: FileStatus

@dataclass
class NormalizedCommit:
    """
    A single commit in a push, in a provider-agnostic format.
    """
    hash: str
    files: Set[FileChange] = field(default_factory=set)
    timestamp: datetime | None = None

    def has_file_changed(self, file_path: str) -> bool:
        """Check if a specific file was changed (added or modified)"""
        return any(
            f.path == file_path and f.status in (FileStatus.ADDED, FileStatus.MODIFIED)
            for f in self.files
        )

    def has_file_added(self, file_path: str) -> bool:
        """Check if a specific file was added"""
        return any(
            f.path == file_path and f.status == FileStatus.ADDED
            for f in self.files
        )

    def get_changed_files(self) -> Set[str]:
        """Returns a unique set of all files that were added or modified"""
        return {
            f.path for f in self.files
            if f.status in (FileStatus.ADDED, FileStatus.MODIFIED)
        }

    def get_files_by_status(self, status: FileStatus) -> List[str]:
        """Get all files with a specific status"""
        return [f.path for f in self.files if f.status == status]

    @property
    def added(self) -> List[str]:
        """Backward compatibility"""
        return self.get_files_by_status(FileStatus.ADDED)

    @property
    def modified(self) -> List[str]:
        """Backward compatibility"""
        return self.get_files_by_status(FileStatus.MODIFIED)

    @property
    def removed(self) -> List[str]:
        """Backward compatibility"""
        return self.get_files_by_status(FileStatus.REMOVED)