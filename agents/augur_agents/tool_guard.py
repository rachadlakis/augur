"""Security checks that run in ADK's ``before_tool_callback``, ahead of every tool.

The tools already enforce the approval gate themselves (``check_policy``). This
module covers what a single tool cannot see, because it needs the whole turn or
the whole session:

1. **No self-approval.** ``grant_approval`` is refused unless the token was
   issued by ``request_approval`` in this session *and* in an earlier turn. A
   human has to reply between the request and the grant, so a model that
   "decides the user would agree" cannot spend money within one turn. A token
   that came from somewhere else, such as a worker's reply or a pasted string,
   cannot be granted at all.
2. **No credentials in arguments.** Tool arguments are logged, written to the
   audit trail and the workflow record, and ``dispatch_task`` sends them to
   another agent over A2A. A call whose arguments contain a live secret from
   this process's environment, or anything shaped like an API key or private
   key, is refused rather than leaked.
3. **Bounded arguments.** One oversized argument (usually prompt-injected
   content being forwarded) is refused before it reaches a tool or a log.
4. **Bounded turns.** There is a cap on tool calls per turn and on identical
   repeats of one call, so a model stuck polling or retrying a refusal stops
   instead of looping until the request times out.

A refusal is returned as an ordinary tool result (``success: false`` with a
readable ``error``), which is the contract every tool here follows: the model
reads why and reacts. Each refusal is also written to the audit trail.

Unlike the logging callbacks, this guard **fails closed**: if a check itself
raises, the call is refused.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections import Counter, OrderedDict
from typing import Any, Optional

from google.adk.tools.base_tool import BaseTool

from augur_agents.config import (
    TOOL_GUARD_MAX_ARG_BYTES,
    TOOL_GUARD_MAX_CALLS_PER_TURN,
    TOOL_GUARD_MAX_REPEAT_CALLS,
)
from augur_agents.tools.governance_tools import record_audit

logger = logging.getLogger("augur.agents.guard")

# Session-state key: approval token -> invocation id of the turn that requested
# it. Kept in session state, not in memory, because the grant arrives on a later
# turn and possibly in a later process.
APPROVAL_REQUESTS_KEY = "guard:approval_requests"
# Only the most recent requests are remembered. An older token can still be
# denied but no longer granted, which is safe.
_MAX_REMEMBERED_REQUESTS = 50

# Credential shapes worth refusing even when the value is not in our env.
_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),  # Anthropic / OpenAI
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key id
    re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),  # GitHub
    re.compile(r"xox[abprs]-[A-Za-z0-9\-]{10,}"),  # Slack
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]
_SECRET_ENV_NAME = re.compile(r"KEY|SECRET|TOKEN|PASSWORD|PASSPHRASE", re.IGNORECASE)
# Shorter env values are too likely to be flags or ids that show up innocently.
_MIN_SECRET_LEN = 16

# invocation id -> Counter of call signatures. Module level for the same reason
# as callbacks._tool_starts: one process per agent server. Bounded so a
# long-running server does not grow without limit.
_turn_calls: OrderedDict[str, Counter[str]] = OrderedDict()
_MAX_TRACKED_TURNS = 1024


def _blocked(tool: BaseTool, tool_context: Any, rule: str, error: str) -> dict[str, Any]:
    agent = getattr(tool_context, "agent_name", "?")
    logger.warning("[guard] %s -> %s BLOCKED (%s): %s", agent, tool.name, rule, error)
    record_audit("tool_call_blocked", agent=agent, tool=tool.name, rule=rule)
    return {"success": False, "error": error, "blocked_by": "tool_guard", "rule": rule}


def _serialize(args: dict[str, Any]) -> str:
    return json.dumps(args or {}, sort_keys=True, default=str, ensure_ascii=False)


def _env_secrets() -> list[str]:
    return [
        value
        for name, value in os.environ.items()
        if _SECRET_ENV_NAME.search(name) and len(value) >= _MIN_SECRET_LEN
    ]


def _contains_secret(text: str) -> bool:
    if any(secret in text for secret in _env_secrets()):
        return True
    return any(p.search(text) for p in _SECRET_PATTERNS)


def _count_call(invocation_id: str, signature: str) -> tuple[int, int]:
    """Record one call; return (calls this turn, identical calls this turn)."""
    counts = _turn_calls.get(invocation_id)
    if counts is None:
        counts = _turn_calls[invocation_id] = Counter()
        while len(_turn_calls) > _MAX_TRACKED_TURNS:
            _turn_calls.popitem(last=False)
    counts[signature] += 1
    return sum(counts.values()), counts[signature]


def _check_grant(args: dict[str, Any], tool_context: Any) -> Optional[str]:
    token = args.get("approval_token")
    requests = tool_context.state.get(APPROVAL_REQUESTS_KEY) or {}
    requested_in = requests.get(token)
    if requested_in is None:
        return (
            f"Approval {token!r} was not requested in this session, so it "
            "cannot be granted here. Call request_approval for the exact action."
        )
    if requested_in == tool_context.invocation_id:
        return (
            "An approval cannot be granted in the same turn it was requested. "
            "Show the request to the user and end your turn. Call "
            "grant_approval only after the user has replied and agreed."
        )
    return None


def guard_before_tool(
    tool: BaseTool, args: dict[str, Any], tool_context: Any
) -> Optional[dict]:
    """Refuse an unsafe tool call. Returns None to let the call run."""
    try:
        text = _serialize(args)

        size = len(text.encode("utf-8"))
        if size > TOOL_GUARD_MAX_ARG_BYTES:
            return _blocked(
                tool, tool_context, "args_too_large",
                f"Arguments are {size} bytes; the limit is "
                f"{TOOL_GUARD_MAX_ARG_BYTES}. Pass a reference (dataset_ref, "
                "job id, report id) instead of the content itself.",
            )

        if _contains_secret(text):
            return _blocked(
                tool, tool_context, "secret_in_args",
                "The arguments contain what looks like a credential. Credentials "
                "must never be passed to tools or other agents. Remove it and "
                "retry; each service reads its own keys from its environment.",
            )

        if tool.name == "grant_approval":
            reason = _check_grant(args, tool_context)
            if reason:
                return _blocked(tool, tool_context, "self_approval", reason)

        total, repeats = _count_call(
            str(tool_context.invocation_id), f"{tool.name}:{text}"
        )
        if total > TOOL_GUARD_MAX_CALLS_PER_TURN:
            return _blocked(
                tool, tool_context, "turn_call_budget",
                f"This turn has used its {TOOL_GUARD_MAX_CALLS_PER_TURN} tool "
                "calls. Report what you have to the user and end the turn.",
            )
        if repeats > TOOL_GUARD_MAX_REPEAT_CALLS:
            return _blocked(
                tool, tool_context, "repeated_call",
                f"{tool.name} has already been called {repeats - 1} times this "
                "turn with these exact arguments. Repeating it will not change "
                "the answer. If you are waiting on work, say so and end the turn.",
            )
    except Exception:
        logger.exception("[guard] check failed for %s; refusing the call", tool.name)
        return {
            "success": False,
            "error": "The tool call could not be safety-checked, so it was not run.",
            "blocked_by": "tool_guard",
            "rule": "guard_error",
        }
    return None


def guard_after_tool(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: Any,
    tool_response: Any,
) -> Optional[dict]:
    """Remember which turn issued each approval token. Never alters the result."""
    try:
        if (
            tool.name == "request_approval"
            and isinstance(tool_response, dict)
            and tool_response.get("success")
        ):
            # Copy and reassign: ADK records a state change only on assignment,
            # not when a nested dict is mutated in place.
            requests = dict(tool_context.state.get(APPROVAL_REQUESTS_KEY) or {})
            requests[tool_response["approval_token"]] = tool_context.invocation_id
            tool_context.state[APPROVAL_REQUESTS_KEY] = dict(
                list(requests.items())[-_MAX_REMEMBERED_REQUESTS:]
            )
    except Exception:  # pragma: no cover - a later grant is then refused, not allowed
        logger.exception("[guard] failed to record approval request")
    return None


def reset_turn_counters() -> None:
    """Forget per-turn call counts. For tests."""
    _turn_calls.clear()


__all__ = [
    "APPROVAL_REQUESTS_KEY",
    "guard_before_tool",
    "guard_after_tool",
    "reset_turn_counters",
]
