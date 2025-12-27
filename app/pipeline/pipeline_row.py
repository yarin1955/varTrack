from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

class RowKind(Enum):
    """
    Represents the operation type for a row, mirroring Apache SeaTunnel/Flink.
    """
    INSERT = auto()  # New configuration key added
    UPDATE = auto()  # Existing key's value changed
    DELETE = auto()  # Key removed
    UNCHANGED = auto()

@dataclass
class PipelineRow:
    """
    Represents a single atomic configuration change.
    """
    key: str                    # e.g., "app/database/port"
    value: Any                  # e.g., 5432 (None for DELETE)
    kind: RowKind               # INSERT, UPDATE, or DELETE
    metadata: Dict[str, Any] = field(default_factory=dict) # Context (env, repo, commit_sha)