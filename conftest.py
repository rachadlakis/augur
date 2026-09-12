"""Repo-root pytest bootstrap.

The only thing here is a sandbox accommodation: in some CI / sandboxed shells the
system temp dir (``%TEMP%`` / ``/tmp``) is not writable, and pytest's ``tmp_path``
fixture then fails at *setup* with ``PermissionError: ... pytest-of-<user>`` -
before any test body runs. ``pytest-asyncio``'s event-loop fixture trips the same
path even for synchronous tests once ``asyncio_mode = "auto"`` is set.

Redirect ``tempfile`` - and therefore ``tmp_path`` - to a repo-local, git-ignored
directory, but only when the default location is actually unusable, so a normal
machine is unaffected. The probe mirrors what pytest itself does: create (and
reuse) a ``pytest-of-<user>`` directory under the temp root.

This is deliberately the *only* root-level test file. ``agents/tests`` and
``dist_kit/tests`` keep their own ``conftest.py``; neither depends on this one.
"""

from __future__ import annotations

import getpass
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
AGENTS_DIR = ROOT / "agents"
for _candidate in (ROOT, AGENTS_DIR):
    _candidate_str = str(_candidate)
    if _candidate_str not in sys.path:
        sys.path.insert(0, _candidate_str)


def _default_tmp_is_usable() -> bool:
    try:
        user = getpass.getuser()
    except Exception:
        user = "unknown"
    probe = Path(tempfile.gettempdir()) / f"pytest-of-{user}"
    try:
        probe.mkdir(exist_ok=True)
        marker = probe / ".mobius-write-probe"
        marker.write_text("ok", encoding="utf-8")
        marker.unlink()
        return True
    except OSError:
        return False


if not _default_tmp_is_usable():
    _local = Path(__file__).parent / ".pytest-tmp"
    _local.mkdir(exist_ok=True)
    tempfile.tempdir = str(_local)
    for _var in ("TMPDIR", "TEMP", "TMP", "PYTEST_DEBUG_TEMPROOT"):
        os.environ[_var] = str(_local)
