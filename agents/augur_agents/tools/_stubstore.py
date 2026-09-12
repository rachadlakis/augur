"""Mutable state behind the stub tools.

There are no MCP capability servers yet, so the tools keep their own state here.
The split is deliberate:

* **Training jobs live in SQLite.** A job is the one thing that must outlive the
  process that created it - the whole long-running design rests on being able to
  submit a job, restart the worker, and still poll it. Keeping jobs in a dict
  would make the polling path a lie that only works while nothing crashes. This
  is the seam a real ``training-mcp`` job manager replaces.
* **Approvals, evaluations and the audit log stay in memory.** They are
  per-session and cheap to recreate, and pretending otherwise would imply a
  durability guarantee this layer does not have.

Nothing here is imported by the agents directly; the tool modules wrap it.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterator

from augur_agents import config

## =============================================================================
# Training job store (SQLite)
## =============================================================================

_DDL = """
CREATE TABLE IF NOT EXISTS jobs (
    id       TEXT PRIMARY KEY,
    payload  TEXT NOT NULL
)
"""


def _db_path() -> str:
    """Filesystem path from the configured sqlite URL.

    ``:memory:`` is honoured so tests can run without touching disk.
    """
    url = config.JOB_STORE_URL
    path = url.split("///", 1)[-1] if "///" in url else url.split("//", 1)[-1]
    return path or ":memory:"


class JobStore:
    """A tiny durable key/value store for ``TrainingJob`` payloads.

    Sqlite rather than a dict so a submitted job survives a worker restart.
    ``check_same_thread=False`` plus a lock because uvicorn serves requests from
    a threadpool and sqlite connections are not thread-safe by default.
    """

    def __init__(self, path: str | None = None) -> None:
        self._path = path or _db_path()
        if self._path not in (":memory:",):
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.execute(_DDL)
        self._conn.commit()
        self._lock = threading.Lock()

    def put(self, job_id: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO jobs (id, payload) VALUES (?, ?) "
                "ON CONFLICT(id) DO UPDATE SET payload = excluded.payload",
                (job_id, json.dumps(payload, default=str)),
            )
            self._conn.commit()

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def all(self) -> Iterator[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT payload FROM jobs").fetchall()
        for (payload,) in rows:
            yield json.loads(payload)

    def clear(self) -> None:
        """Tests only."""
        with self._lock:
            self._conn.execute("DELETE FROM jobs")
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()


_job_store: JobStore | None = None


def job_store() -> JobStore:
    """The process-wide job store (created on first use)."""
    global _job_store
    if _job_store is None:
        _job_store = JobStore()
    return _job_store


def reset_job_store(path: str | None = None) -> JobStore:
    """Point the store at a new location and clear it. Tests only."""
    global _job_store
    if _job_store is not None:
        _job_store.close()
    _job_store = JobStore(path)
    return _job_store


## =============================================================================
# In-memory stores
#
# Per-process and intentionally not durable: an approval that silently survived
# a restart would be a security smell, not a feature.
## =============================================================================

_approvals: dict[str, dict[str, Any]] = {}
_evaluations: dict[str, dict[str, Any]] = {}
_artifacts: dict[str, dict[str, Any]] = {}
_audit: list[dict[str, Any]] = []


def approvals() -> dict[str, dict[str, Any]]:
    return _approvals


def evaluations() -> dict[str, dict[str, Any]]:
    return _evaluations


def artifacts() -> dict[str, dict[str, Any]]:
    return _artifacts


def audit() -> list[dict[str, Any]]:
    return _audit


def reset_all(job_store_path: str | None = ":memory:") -> None:
    """Wipe every stub store. Tests only."""
    _approvals.clear()
    _evaluations.clear()
    _artifacts.clear()
    _audit.clear()
    reset_job_store(job_store_path)


__all__ = [
    "JobStore",
    "job_store",
    "reset_job_store",
    "approvals",
    "evaluations",
    "artifacts",
    "audit",
    "reset_all",
]

