from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set, Any
from enum import Enum

from app.models.rule import Rule
from app.pipeline.source import Source
from app.pipeline.sink import Sink
from app.pipeline.transforms.parser import ContentParser
from app.pipeline.transforms.flattener import Flattenizer
from app.business_logic.compare_states import compare_states
from app.pipeline.pipeline_row import PipelineRow, RowKind


class DriftType(Enum):
    MISSING_IN_DB = "missing_in_db"
    EXTRA_IN_DB = "extra_in_db"
    VALUE_MISMATCH = "value_mismatch"


@dataclass
class DriftItem:
    key: str
    drift_type: DriftType
    git_value: Any = None
    db_value: Any = None
    file_path: str = ""
    unique_key: str = ""
    environment: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ReconciliationReport:
    repository: str
    branch: str
    total_files_checked: int = 0
    total_keys_checked: int = 0
    drift_detected: List[DriftItem] = field(default_factory=list)
    fixes_applied: List[DriftItem] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None
    dry_run: bool = False

    @property
    def drift_count(self) -> int: return len(self.drift_detected)

    @property
    def fixed_count(self) -> int: return len(self.fixes_applied)

    def summary(self) -> Dict[str, Any]:
        return {
            "repository": self.repository,
            "duration": (self.end_time - self.start_time).total_seconds() if self.end_time else 0,
            "drift_detected": self.drift_count,
            "fixes_applied": self.fixed_count,
            "errors": len(self.errors)
        }


class SelfHealingManager:
    def __init__(self, source: Source, sink: Sink, rule: Rule, parser=None, flattener=None):
        self.source = source
        self.sink = sink
        self.rule = rule
        self.parser = parser or ContentParser()
        self.flattener = flattener or Flattenizer(root_key="varTrack")

    def _check_file_drift(self, repository: str, branch: str, file_path: str) -> List[DriftItem]:
        items = []
        meta = self.rule.get_unique_key_and_env(file_path, branch)

        # 1. Fetch State
        git_raw = self.source.get_file_from_commit(repository, branch, file_path)
        git_flat = self.flattener.process(self.parser.process(git_raw))
        db_state = self.sink.fetch(meta) or {}

        # 2. Compare
        diff = compare_states(current_data=git_flat, old_data=db_state)

        # 3. Map to DriftItems
        for k, v in diff['added'].items():
            items.append(DriftItem(k, DriftType.MISSING_IN_DB, git_value=v, file_path=file_path, **meta))
        for k, v in diff['changed'].items():
            items.append(
                DriftItem(k, DriftType.VALUE_MISMATCH, git_value=v, db_value=db_state.get(k), file_path=file_path,
                          **meta))
        for k, v in diff['deleted'].items():
            items.append(DriftItem(k, DriftType.EXTRA_IN_DB, db_value=db_state.get(k), file_path=file_path, **meta))

        return items

    def reconcile(self, repository: str, branch: str, files: List[str] = None, dry_run=False,
                  auto_fix=True) -> ReconciliationReport:
        report = ReconciliationReport(repository=repository, branch=branch, dry_run=dry_run)
        files_to_check = files or ([self.rule.fileName] if self.rule.fileName else [])

        for path in files_to_check:
            try:
                drift = self._check_file_drift(repository, branch, path)
                report.drift_detected.extend(drift)
                report.total_files_checked += 1
            except Exception as e:
                report.errors.append(f"Error checking {path}: {str(e)}")

        if not dry_run and auto_fix:
            self._apply_fixes(report)

        report.end_time = datetime.utcnow()
        return report

    def _apply_fixes(self, report: ReconciliationReport):
        for item in report.drift_detected:
            # 🛡️ PRUNE PROTECTION CHECK
            if item.drift_type == DriftType.EXTRA_IN_DB and self.rule.is_protected_from_prune(item.key):
                continue

            kind = RowKind.INSERT if item.drift_type == DriftType.MISSING_IN_DB else \
                RowKind.UPDATE if item.drift_type == DriftType.VALUE_MISMATCH else RowKind.DELETE

            row = PipelineRow(key=item.key, value=item.git_value, kind=kind,
                              metadata={'unique_key': item.unique_key, 'env': item.environment})
            try:
                self.sink.write(row)
                report.fixes_applied.append(item)
            except Exception as e:
                report.errors.append(f"Failed to fix {item.key}: {e}")

        self.sink.flush()