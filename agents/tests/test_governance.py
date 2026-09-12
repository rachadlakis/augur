"""The approval gate.

These are the most important tests in the suite: they pin the property that an
approval authorizes one exact action and cannot be stretched to cover a
different, more expensive one.
"""

from __future__ import annotations

import pytest

from augur_agents.tools import _stubstore
from augur_agents.tools import governance_tools as g

PARAMS = {"plan_digest": "abc123", "gpu_count": 1, "cost_usd": 6.0}


def test_read_only_actions_need_no_approval():
    assert g.check_policy("inspect_dataset", {"source": "wikitext"})["allowed"]
    assert g.check_policy("run_evaluation", {"model": "m"})["allowed"]


def test_read_only_actions_cannot_request_approval():
    """Asking for approval to read something is a mistake worth naming."""
    result = g.request_approval("inspect_dataset", {"source": "wikitext"})
    assert not result["success"]
    assert "read-only" in result["error"]


class TestApprovalRequired:
    def test_no_token_is_refused_with_a_usable_explanation(self):
        decision = g.check_policy("submit_training_job", PARAMS)
        assert not decision["allowed"]
        assert "request_approval" in decision["reason"]

    def test_unknown_token_is_refused(self):
        decision = g.check_policy("submit_training_job", PARAMS, "appr_nonexistent")
        assert not decision["allowed"]
        assert "Unknown approval token" in decision["reason"]

    def test_requested_but_not_granted_is_refused(self):
        token = g.request_approval("submit_training_job", PARAMS)["approval_token"]
        decision = g.check_policy("submit_training_job", PARAMS, token)
        assert not decision["allowed"]
        assert "not been granted" in decision["reason"]

    def test_granted_with_matching_params_is_allowed(self, approved):
        token = approved("submit_training_job", PARAMS)
        assert g.check_policy("submit_training_job", PARAMS, token)["allowed"]


class TestDigestBinding:
    """Changing the action invalidates the approval, without anyone noticing."""

    @pytest.mark.parametrize(
        "tampered",
        [
            pytest.param({**PARAMS, "gpu_count": 64}, id="more_gpus"),
            pytest.param({**PARAMS, "cost_usd": 6000.0}, id="higher_cost"),
            pytest.param({**PARAMS, "plan_digest": "different"}, id="different_plan"),
            pytest.param({"plan_digest": "abc123"}, id="dropped_parameters"),
        ],
    )
    def test_changed_parameters_are_refused(self, approved, tampered):
        token = approved("submit_training_job", PARAMS)
        decision = g.check_policy("submit_training_job", tampered, token)
        assert not decision["allowed"]
        assert "does not match" in decision["reason"]

    def test_a_token_cannot_be_spent_on_a_different_action(self, approved):
        token = approved("submit_training_job", PARAMS)
        decision = g.check_policy("cancel_training_job", PARAMS, token)
        assert not decision["allowed"]
        assert "is for" in decision["reason"]

    def test_a_mismatch_is_audited(self, approved):
        token = approved("submit_training_job", PARAMS)
        g.check_policy("submit_training_job", {**PARAMS, "gpu_count": 64}, token)
        assert any(
            e["event"] == "approval_digest_mismatch" for e in _stubstore.audit()
        )

    def test_a_refused_check_does_not_burn_the_approval(self, approved):
        """A tampered attempt must not lock out the legitimate one."""
        token = approved("submit_training_job", PARAMS)
        g.check_policy("submit_training_job", {**PARAMS, "gpu_count": 64}, token)
        assert g.check_policy("submit_training_job", PARAMS, token)["allowed"]


class TestSingleUse:
    def test_an_approval_cannot_be_replayed(self, approved):
        token = approved("submit_training_job", PARAMS)
        assert g.check_policy("submit_training_job", PARAMS, token)["allowed"]
        second = g.check_policy("submit_training_job", PARAMS, token)
        assert not second["allowed"]
        assert "already been spent" in second["reason"]

    def test_consume_false_leaves_it_spendable(self, approved):
        token = approved("submit_training_job", PARAMS)
        assert g.check_policy("submit_training_job", PARAMS, token, consume=False)["allowed"]
        assert g.check_policy("submit_training_job", PARAMS, token)["allowed"]


class TestExpiry:
    def test_an_expired_approval_is_refused(self):
        token = g.request_approval(
            "submit_training_job", PARAMS, ttl_minutes=0
        )["approval_token"]
        g.grant_approval(token)
        decision = g.check_policy("submit_training_job", PARAMS, token)
        assert not decision["allowed"]
        assert "expired" in decision["reason"]


class TestDenial:
    def test_a_denied_approval_can_never_be_granted_afterwards(self):
        token = g.request_approval("submit_training_job", PARAMS)["approval_token"]
        g.deny_approval(token, reason="too expensive")

        assert not g.grant_approval(token)["success"]
        assert not g.check_policy("submit_training_job", PARAMS, token)["allowed"]


def test_the_audit_trail_records_the_decision_sequence(approved):
    token = approved("submit_training_job", PARAMS)
    g.check_policy("submit_training_job", PARAMS, token)
    events = [e["event"] for e in _stubstore.audit()]
    assert events == [
        "approval_requested", "approval_granted", "approval_consumed"
    ]


def test_every_mutating_tool_has_a_declared_risk_class():
    """A tool missing from the registry would default to 'paid' silently."""
    for action in (
        "materialize_dataset", "submit_training_job",
        "cancel_training_job", "resume_training_job",
    ):
        assert action in g.ACTION_RISK
        assert g.ACTION_RISK[action] != "read_only"

