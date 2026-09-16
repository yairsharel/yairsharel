"""Remembers which papers we have already sent, so nobody gets a duplicate."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

# Papers stay in the file for this long. Long enough that a slow-to-index
# record can never come round twice; short enough that the file stays small.
RETENTION_DAYS = 400


class SeenWorks:
    def __init__(self, path: Path):
        self.path = path
        self.last_run: str | None = None
        self.seen: dict[str, str] = {}
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8") or "{}")
            self.last_run = data.get("last_run")
            self.seen = data.get("seen") or {}

    def __contains__(self, work_id: str) -> bool:
        return work_id in self.seen

    def add(self, work_id: str, when: date | None = None) -> None:
        self.seen[work_id] = (when or date.today()).isoformat()

    def prune(self, today: date | None = None) -> int:
        cutoff = (today or date.today()) - timedelta(days=RETENTION_DAYS)
        stale = [k for k, v in self.seen.items() if _as_date(v) < cutoff]
        for key in stale:
            del self.seen[key]
        return len(stale)

    def save(self) -> None:
        removed = self.prune()
        if removed:
            log.info("Pruned %d entries older than %d days", removed, RETENTION_DAYS)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "last_run": datetime.now().isoformat(timespec="seconds"),
            # Sorted so a git diff of this file shows only the real changes.
            "seen": dict(sorted(self.seen.items())),
        }
        self.path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _as_date(value: str) -> date:
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return date.today()
