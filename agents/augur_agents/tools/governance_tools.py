"""Approval and policy enforcement.

The rule this module exists to enforce: **an approval authorizes one exact
action, not a category of actions.** A human approving "train gpt2 on wikitext-2
across 1 GPU for about $6" has not approved the same run across 64 GPUs, and a
free-form "yes go ahead" in chat is not an authorization token at all.

That is implemented by binding every approval to an **action digest** - a sha256
over the action name plus its canonical parameters. ``check_policy`` recomputes
the digest from the parameters the tool was *actually* called with and refuses
if it differs. Changing the model, dataset, GPU count, destination or cost
therefore invalidates the approval automatically, rather than relying on anyone
noticing.

This is enforcement in code. The agent instructions describe the same rules, but
a tool description is not a safety mechanism: an agent that ignores its prompt
still cannot spend an approval that does not match.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from augur_agents.contracts import ApprovalRequest, digest_of
from augur_agents.tools import _stubstore

logger = logging.getLogger("augur.agents.governance")

# How long an unused approval stays spendable. Short on purpose: an approval is
# a decision about a specific moment (this cost, this cluster, this dataset),
# and stale authorization is how surprise bills happen.
DEFAULT_TTL_MINUTES = 30

# Risk class per action. Read-only actions need no approval; everything that
# spends money, destroys state, or publishes does.
ACTION_RISK: dict[str, str] = {
    # read-only
    "inspect_dataset": "read_only",
    "validate_dataset": "read_only",
    "build_manifest": "read_only",
    "recommend_parallelism": "read_only",
    "validate_training_plan": "read_only",
    "estimate_training_job": "read_only",
    "get_training_status": "read_only",
    "stream_training_logs": "read_only",
    "run_evaluation": "read_only",
    "get_evaluation_report": "read_only",
    "compare_candidates": "read_only",
    "search_papers": "read_only",
    "get_paper": "read_only",
    "summarize_findings": "read_only",
    # mutating
    "materialize_dataset": "paid",
    "submit_training_job": "paid",
    "resume_training_job": "paid",
    "cancel_training_job": "destructive",
    "publish_dataset": "public",
    "publish_model": "public",
}

READ_ONLY_ACTIONS = frozenset(a for a, r in ACTION_RISK.items() if r == "read_only")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def compute_action_digest(action: str, params: dict[str, Any]) -> str:
    """The canonical identity of one action-with-parameters.

    Both the request and the later check go through here, so the two can never
    disagree about how a payload is serialized.
    """
    return digest_of({"action": action, "params": params})


def record_audit(event: str, **fields: Any) -> dict[str, Any]:
    """Append to the audit log. Always succeeds."""
    entry = {"at": _now().isoformat(), "event": event, **fields}
    _stubstore.audit().append(entry)
    logger.info("[audit] %s %s", event, fields)
    return entry


def request_approval(
    action: str,
    params: dict[str, Any] | None = None,
    summary: str = "",
    estimate: dict[str, Any] | None = None,
    ttl_minutes: int = DEFAULT_TTL_MINUTES,
) -> dict[str, Any]:
    """Create a pending approval for one exact action.

    Returns the request for the orchestrator to put in front of a human. The
    returned ``approval_token`` is NOT yet spendable - it becomes spendable only
    after :func:`grant_approval`.

    Args:
        action: the tool that will be called, e.g. ``"submit_training_job"``.
        params: the exact arguments it will be called with. These are what the
            digest is computed over, so they must be the real ones.
        summary: one line a human can actually make a decision from.
        estimate: cost/time/resource prediction to show alongside.
        ttl_minutes: how long the approval stays spendable once granted.
    """
    params = params or {}
    risk = ACTION_RISK.get(action, "paid")
    if risk == "read_only":
        return {
            "success": False,
            "error": (
                f"{action!r} is read-only and needs no approval. Just call it."
            ),
        }

    req = ApprovalRequest(
        action=action,
        action_digest=compute_action_digest(action, params),
        risk=risk,  # type: ignore[arg-type]
        summary=summary,
        estimate=estimate or {},
        expires_at=_now() + timedelta(minutes=ttl_minutes),
    )
    _stubstore.approvals()[req.id] = req.model_dump(mode="json")
    record_audit("approval_requested", approval_id=req.id, action=action, risk=risk)
    return {
        "success": True,
        "approval_token": req.id,
        "action": action,
        "risk": risk,
        "summary": summary,
        "estimate": req.estimate,
        "action_digest": req.action_digest,
        "expires_at": req.expires_at.isoformat() if req.expires_at else None,
        "status": "pending",
        "note": (
            "Show this to the user and wait for an explicit decision. "
            "Call grant_approval only with what the user actually said."
        ),
    }


def grant_approval(approval_token: str, granted_by: str = "user") -> dict[str, Any]:
    """Mark an approval as granted by a human."""
    raw = _stubstore.approvals().get(approval_token)
    if raw is None:
        return {"success": False, "error": f"No approval {approval_token!r}."}
    req = ApprovalRequest.model_validate(raw)
    if req.consumed:
        return {"success": False, "error": "That approval has already been spent."}
    req.granted = True
    req.granted_by = granted_by
    req.granted_at = _now()
    _stubstore.approvals()[approval_token] = req.model_dump(mode="json")
    record_audit("approval_granted", approval_id=req.id, action=req.action,
                 granted_by=granted_by)
    return {
        "success": True,
        "approval_token": approval_token,
        "action": req.action,
        "status": "granted",
        "expires_at": req.expires_at.isoformat() if req.expires_at else None,
    }


def deny_approval(approval_token: str, reason: str = "") -> dict[str, Any]:
    """Record that a human refused. The token can never be spent afterwards."""
    raw = _stubstore.approvals().get(approval_token)
    if raw is None:
        return {"success": False, "error": f"No approval {approval_token!r}."}
    req = ApprovalRequest.model_validate(raw)
    req.granted = False
    req.consumed = True  # burn it, so it cannot be granted later by accident
    _stubstore.approvals()[approval_token] = req.model_dump(mode="json")
    record_audit("approval_denied", approval_id=req.id, action=req.action, reason=reason)
    return {"success": True, "approval_token": approval_token, "status": "denied",
            "reason": reason}


def check_policy(
    action: str,
    params: dict[str, Any] | None = None,
    approval_token: str | None = None,
    *,
    consume: bool = True,
) -> dict[str, Any]:
    """Decide whether ``action`` may run with ``params``.

    Called by every mutating tool before it does anything. Returns
    ``{"allowed": bool, ...}``; when allowed and ``consume`` is set, the
    approval is spent so the same token cannot launch a second job.
    """
    params = params or {}
    risk = ACTION_RISK.get(action, "paid")

    if risk == "read_only":
        return {"allowed": True, "risk": risk, "reason": "read-only action"}

    if not approval_token:
        return {
            "allowed": False,
            "risk": risk,
            "reason": (
                f"{action!r} is a {risk} action and needs human approval. "
                f"Call request_approval({action!r}, params=...) with the exact "
                f"arguments, show the user the estimate, and pass the returned "
                f"approval_token once they agree."
            ),
        }

    raw = _stubstore.approvals().get(approval_token)
    if raw is None:
        return {"allowed": False, "risk": risk,
                "reason": f"Unknown approval token {approval_token!r}."}
    req = ApprovalRequest.model_validate(raw)

    if not req.granted:
        return {"allowed": False, "risk": risk,
                "reason": "That approval has not been granted by a human yet."}
    if req.consumed:
        return {"allowed": False, "risk": risk,
                "reason": "That approval has already been spent. Request a new one."}
    if req.expires_at is not None and _now() >= req.expires_at:
        return {"allowed": False, "risk": risk,
                "reason": f"That approval expired at {req.expires_at.isoformat()}."}
    if req.action != action:
        return {"allowed": False, "risk": risk,
                "reason": (f"That approval is for {req.action!r}, "
                           f"not {action!r}.")}

    # The check that does the real work: the parameters must be the ones that
    # were approved, not merely the same action name.
    expected = compute_action_digest(action, params)
    if expected != req.action_digest:
        record_audit("approval_digest_mismatch", approval_id=req.id, action=action)
        return {
            "allowed": False,
            "risk": risk,
            "reason": (
                "The approval does not match these parameters - something "
                "changed (model, dataset, GPU count, cost, destination) since "
                "the user approved it. Request approval again for the new plan."
            ),
        }

    if consume:
        req.consumed = True
        _stubstore.approvals()[approval_token] = req.model_dump(mode="json")
    record_audit("approval_consumed", approval_id=req.id, action=action)
    return {"allowed": True, "risk": risk, "reason": "approved",
            "approval_token": approval_token}


def list_audit(limit: int = 50) -> dict[str, Any]:
    """The audit trail so far. Read-only."""
    entries = _stubstore.audit()[-limit:]
    return {"success": True, "count": len(entries), "entries": entries}


# Tools the ORCHESTRATOR gets. The workers never issue approvals - they only
# have them checked - so this set is not handed to a worker agent.
GOVERNANCE_TOOLS = [request_approval, grant_approval, deny_approval, list_audit]


__all__ = [
    "ACTION_RISK",
    "READ_ONLY_ACTIONS",
    "compute_action_digest",
    "request_approval",
    "grant_approval",
    "deny_approval",
    "check_policy",
    "record_audit",
    "list_audit",
    "GOVERNANCE_TOOLS",
]

