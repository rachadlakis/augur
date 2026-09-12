"""Shared fixtures. Every test here is offline.

No network, no LLM calls, no real services: credentials are obviously fake so
nothing can accidentally reach a live provider, and the orchestrator's
auto-connect is disabled so importing its module never tries to fetch a card.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# The system temp dir is not writable in a sandboxed session (CLAUDE.md notes
# this), which breaks pytest's tmp_path fixture. Point tempfile - and therefore
# tmp_path - at a repo-local, git-ignored directory before pytest reads it.
_TMP = Path(__file__).resolve().parent.parent / ".pytest-tmp"
_TMP.mkdir(exist_ok=True)
tempfile.tempdir = str(_TMP)
for _v in ("TMPDIR", "TEMP", "TMP"):
    os.environ[_v] = str(_TMP)

# Set before importing anything from augur_agents: config reads the environment
# at import time.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-not-a-real-key")
os.environ.setdefault("LLM_PROVIDER", "anthropic")
os.environ.setdefault("DEFAULT_MODEL", "claude-haiku-4-5-20251001")
os.environ.setdefault("USER_ID", "test_user")
os.environ.setdefault("TENANT_ID", "test_tenant")
# Keep the orchestrator module importable without live workers.
os.environ["MOBIUS_ORCHESTRATOR_AUTOINIT"] = "0"
# Stub jobs finish fast so the lifecycle is exercised without slow tests.
os.environ.setdefault("STUB_TRAINING_DURATION_SECONDS", "1")


@pytest.fixture(autouse=True)
def clean_stores():
    """Wipe the stub stores around every test.

    The job store goes to :memory: so tests never touch the real
    mobius_jobs.db, and one test's jobs can never leak into another's.
    """
    from augur_agents.tools import _stubstore  # type: ignore[import-untyped]

    _stubstore.reset_all(":memory:")
    yield
    _stubstore.reset_all(":memory:")


@pytest.fixture
def approved():
    """Grant an approval for one action and return a spendable token."""
    from augur_agents.tools import governance_tools as g

    def _grant(action: str, params: dict) -> str:
        req = g.request_approval(action, params, summary=f"test approval for {action}")
        g.grant_approval(req["approval_token"])
        return req["approval_token"]

    return _grant


@pytest.fixture
def sample_plan():
    """A small, valid, runnable TrainingPlan."""
    from augur_agents.contracts import (  # type: ignore[import-untyped]
        ParallelismConfig,
        TrainingPlan,
    )

    return TrainingPlan(
        project_ref="proj_test",
        dataset_ref="ds_test",
        base_model="gpt2",
        param_count_b=0.124,
        hidden_size=768,
        num_layers=12,
        num_heads=12,
        parallelism=ParallelismConfig(
            strategy="solo", zero_stage=3, dp=1, mbs=1, grad_accum=8, gbs=8
        ),
    )


@pytest.fixture
def tool_context():
    """A stand-in for ADK's ToolContext exposing just `.state`.

    The orchestrator's lifecycle tools only touch `state`, so a namespace with a
    dict is enough and keeps these tests free of ADK runtime setup.
    """

    class FakeToolContext:
        def __init__(self) -> None:
            self.state: dict = {}

    return FakeToolContext()

