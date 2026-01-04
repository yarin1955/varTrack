import time
import threading
from datetime import datetime
from typing import Dict, Optional, Any
from app.business_logic.self_healing import SelfHealingManager, ReconciliationReport


class ReconciliationSchedule:
    def __init__(self, repository, branch, interval):
        self.repository = repository
        self.branch = branch
        self.interval = interval
        self.enabled = True
        self.last_run: Optional[datetime] = None
        self.last_report: Optional[ReconciliationReport] = None
        self.consecutive_errors = 0
        self.max_consecutive_errors = 3


class ReconciliationService:
    def __init__(self):
        self._schedules: Dict[str, ReconciliationSchedule] = {}
        self._managers: Dict[str, SelfHealingManager] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def register_repository(self, repository, branch, source, sink, rule, interval=300):
        key = f"{repository}:{branch}"
        with self._lock:
            self._schedules[key] = ReconciliationSchedule(repository, branch, interval)
            self._managers[key] = SelfHealingManager(source, sink, rule)

    def start(self):
        with self._lock:
            if not self._running:
                self._running = True
                self._thread = threading.Thread(target=self._run_loop, daemon=True)
                self._thread.start()

    def _run_loop(self):
        while self._running:
            now = datetime.utcnow()
            with self._lock:
                keys = list(self._schedules.keys())

            for key in keys:
                sched = self._schedules[key]
                if not sched.enabled: continue

                if sched.last_run is None or (now - sched.last_run).total_seconds() >= sched.interval:
                    self._execute_sync(key, sched)

            time.sleep(10)

    def _execute_sync(self, key, sched):
        try:
            report = self._managers[key].reconcile(sched.repository, sched.branch)
            sched.last_run = datetime.utcnow()
            sched.last_report = report

            if report.errors:
                sched.consecutive_errors += 1
            else:
                sched.consecutive_errors = 0

            if sched.consecutive_errors >= sched.max_consecutive_errors:
                sched.enabled = False
        except Exception:
            sched.consecutive_errors += 1

    def get_status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "schedules": {k: {"enabled": v.enabled, "last_run": v.last_run.isoformat() if v.last_run else None,
                              "errors": v.consecutive_errors} for k, v in self._schedules.items()}
        }

    # API control methods
    def enable_schedule(self, repo, branch):
        self._schedules[f"{repo}:{branch}"].enabled = True

    def disable_schedule(self, repo, branch):
        self._schedules[f"{repo}:{branch}"].enabled = False


reconciliation_service = ReconciliationService()