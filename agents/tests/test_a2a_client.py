"""The orchestrator's A2A client - the resilience paths.

The happy path (real dispatch -> task id -> get_task -> terminal state) is
exercised end to end against live `to_a2a` servers in test_servers_smoke and in
manual verification. What this file pins is the behaviour when a worker is
missing, unreachable, slow or flaky: **every path returns a dict, never raises**,
so one bad worker degrades the answer instead of ending the turn.
"""

from __future__ import annotations

import httpx
import pytest

from augur_agents import registry
from augur_agents.a2a_client import (
    AgentDirectory,
    get_directory,
    reset_directory,
    state_name,
)

EP = [
    registry.AgentEndpoint("data", "http://127.0.0.1:59990"),
    registry.AgentEndpoint("training", "http://127.0.0.1:59991"),
]


@pytest.fixture
def directory():
    """A directory pointed at ports nothing is listening on."""
    reset_directory()
    d = AgentDirectory(endpoints=list(EP))
    yield d
    reset_directory()


async def test_get_directory_is_cached():
    reset_directory()
    assert get_directory() is get_directory()
    reset_directory()


class TestListAgents:
    async def test_unreachable_agents_are_reported_not_hidden(self, directory):
        agents = await directory.list_agents()
        assert {a["name"] for a in agents} == {"data", "training"}
        assert all(a["available"] is False for a in agents)
        assert all(a["error"] for a in agents)

    async def test_the_roster_shape_is_stable_even_when_all_are_down(self, directory):
        for a in await directory.list_agents():
            assert set(a) >= {"name", "available", "url"}


class TestDispatchNeverRaises:
    async def test_unknown_agent_returns_an_error_dict_with_the_known_names(
        self, directory
    ):
        out = await directory.dispatch_task("nonexistent", "do a thing")
        assert out["success"] is False
        assert "data" in out["error"] and "training" in out["error"]

    async def test_an_unreachable_agent_fails_the_health_check_fast(self, directory):
        out = await directory.dispatch_task("data", "do a thing", wait_seconds=1)
        assert out["success"] is False
        assert "health check" in out["error"]

    async def test_get_task_on_an_unknown_agent_returns_an_error_dict(self, directory):
        out = await directory.get_task("nonexistent", "task-1")
        assert out["success"] is False

    async def test_get_task_on_an_unreachable_agent_returns_an_error_dict(
        self, directory
    ):
        out = await directory.get_task("data", "task-1")
        assert out["success"] is False
        assert "task-1" in out["error"]


class TestRetryPolicy:
    """Transient failures get one retry; timeouts and 4xx do not."""

    async def _dispatch_with(self, directory, monkeypatch, side_effect):
        calls = {"n": 0}

        async def fake_reachable(_endpoint):
            return True

        async def fake_send_once(*_a, **_kw):
            calls["n"] += 1
            raise side_effect

        monkeypatch.setattr(directory, "_is_reachable", fake_reachable)
        monkeypatch.setattr(directory, "_send_once", fake_send_once)
        monkeypatch.setattr(
            "augur_agents.config.A2A_RETRY_BACKOFF_SECONDS", 0.0
        )
        out = await directory.dispatch_task("data", "x", wait_seconds=1)
        return out, calls["n"]

    async def test_a_connection_error_is_retried_once(self, directory, monkeypatch):
        out, n = await self._dispatch_with(
            directory, monkeypatch, httpx.ConnectError("refused")
        )
        assert out["success"] is False
        assert n == 2, "one retry"

    async def test_a_timeout_is_not_retried(self, directory, monkeypatch):
        out, n = await self._dispatch_with(
            directory, monkeypatch, httpx.ReadTimeout("slow")
        )
        assert out["success"] is False
        assert n == 1
        assert "did not respond within" in out["error"]

    async def test_an_unexpected_exception_still_returns_a_dict(
        self, directory, monkeypatch
    ):
        out, _ = await self._dispatch_with(
            directory, monkeypatch, RuntimeError("something odd")
        )
        assert out["success"] is False
        assert "RuntimeError" in out["error"]


class TestHealthCheckToggle:
    async def test_setting_the_timeout_to_zero_disables_the_probe(
        self, directory, monkeypatch
    ):
        monkeypatch.setattr(
            "augur_agents.config.A2A_HEALTHCHECK_TIMEOUT_SECONDS", 0.0
        )
        # With the probe off, dispatch proceeds to _send_once and fails there
        # (still a dict) rather than at the health check.
        out = await directory.dispatch_task("data", "x", wait_seconds=1)
        assert out["success"] is False
        assert "health check" not in out["error"]


def test_state_name_never_raises_on_an_unexpected_value():
    # It is used to build a user-facing payload, so it must degrade to a
    # string rather than throw on anything odd.
    assert isinstance(state_name(0), str)
    assert isinstance(state_name(None), str)
    assert isinstance(state_name("garbage"), str)

