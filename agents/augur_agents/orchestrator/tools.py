"""The orchestrator's tools.

These are what make the orchestrator a *driver* rather than a router that hands
off. Each one returns a plain dict; the orchestrator reads it as an ordinary
tool result and carries on reasoning, still in control of the conversation.

Three groups:

* **Delegation** - `list_agents`, `dispatch_task`, `get_task`. Workers are
  reached over A2A and answer; they never take over the conversation.
* **Lifecycle** - `get_workflow`, `advance_stage`. The pipeline's position is
  read from and written to a persisted record, not remembered by the model.
  This is what lets a run that is mid-training survive the end of a turn.
* **Governance** - re-exported from `governance_tools`. Only the orchestrator
  issues approvals; workers only ever have them checked.

All of these take a ``ToolContext`` so they can reach ADK session state, which
is where the workflow record lives.
"""

from __future__ import annotations

import logging
from typing import Any

from google.adk.tools.tool_context import ToolContext

from augur_agents import a2a_client, lifecycle
from augur_agents.tools.governance_tools import (
    deny_approval,
    grant_approval,
    list_audit,
    request_approval,
)

logger = logging.getLogger("augur.agents.orchestrator")


## =============================================================================
# Delegation
## =============================================================================


async def list_agents() -> dict[str, Any]:
    """Which specialist agents exist and what each one can do.

    Call this before delegating. Route on the returned skills rather than on a
    hard-coded name: the roster is configuration, so a new agent can appear
    without any change here. An agent with ``available: false`` is down - say
    so rather than pretending its capability never existed.
    """
    agents = await a2a_client.get_directory().list_agents()
    return {
        "success": True,
        "count": len(agents),
        "agents": agents,
        "note": (
            "Pick the agent whose skills match the sub-task. If the one you "
            "need is unavailable, report that plainly and continue with what "
            "the others can do."
        ),
    }


async def dispatch_task(
    agent_name: str,
    instruction: str,
    tool_context: ToolContext,
    description: str = "",
) -> dict[str, Any]:
    """Send one sub-task to a specialist agent and get its answer.

    Returns as soon as the worker finishes *or* as soon as it is clear the work
    will take a while. In the second case the result carries `state: "working"`
    and a `task_id`: record it, tell the user what is running, and end the turn.
    You can pick the task back up with `get_task` on a later turn - the work
    continues without you holding the call open.

    Args:
        agent_name: from `list_agents`.
        instruction: the complete sub-task. The worker cannot see this
            conversation, so include every reference it needs (dataset_ref,
            plan digest, job id, approval token).
        description: a short label for the workflow record.
    """
    directory = a2a_client.get_directory()
    # Reuse this worker's conversation id so it can remember earlier turns.
    context_key = f"context_id:{agent_name}"
    context_id = tool_context.state.get(context_key)

    result = await directory.dispatch_task(
        agent_name, instruction, context_id=context_id
    )

    if result.get("success"):
        if result.get("context_id"):
            tool_context.state[context_key] = result["context_id"]
        # A task still running is recorded on the workflow so a later turn -
        # or a later process - knows what to poll.
        if not result.get("is_terminal") and result.get("task_id"):
            record = lifecycle.load(tool_context.state)
            if record is not None:
                record.set_pending(
                    agent=agent_name,
                    task_id=result["task_id"],
                    context_id=result.get("context_id"),
                    description=description or instruction[:120],
                )
                lifecycle.save(tool_context.state, record)
    return result


async def get_task(
    agent_name: str, task_id: str, tool_context: ToolContext
) -> dict[str, Any]:
    """Check on a task dispatched earlier, possibly on a previous turn.

    This is how you wait for long work: ask again, rather than blocking. If the
    task is still `working`, say so and stop - do not poll in a loop.
    """
    result = await a2a_client.get_directory().get_task(agent_name, task_id)
    if result.get("success") and result.get("is_terminal"):
        record = lifecycle.load(tool_context.state)
        if record is not None and record.pending and record.pending.task_id == task_id:
            record.pending = None
            lifecycle.save(tool_context.state, record)
    return result


## =============================================================================
# Lifecycle
## =============================================================================


def get_workflow(tool_context: ToolContext) -> dict[str, Any]:
    """Where this project has got to.

    **Call this first on every turn.** It is the source of truth for the current
    stage, the artifact references produced so far, and any task still running -
    all of which outlive your context window and survive a restart.
    """
    record = lifecycle.load(tool_context.state)
    if record is None:
        return {
            "success": True,
            "exists": False,
            "note": (
                "No workflow yet. Call start_workflow with a short project "
                "objective before delegating anything."
            ),
        }
    return {
        "success": True,
        "exists": True,
        "stage": record.stage.value,
        "next_action": lifecycle.NEXT_ACTION.get(record.stage, "done"),
        "allowed_transitions": sorted(
            s.value for s in lifecycle.TRANSITIONS.get(record.stage, ())
        ),
        "refs": {
            "dataset_ref": record.dataset_ref,
            "plan_ref": record.plan_ref,
            "plan_digest": record.plan_digest,
            "approval_ref": record.approval_ref,
            "job_ref": record.job_ref,
            "model_ref": record.model_ref,
            "report_ref": record.report_ref,
        },
        "pending_task": record.pending.model_dump(mode="json") if record.pending else None,
        "is_terminal": record.is_terminal,
        "audit_entries": len(record.audit),
    }


def start_workflow(project_ref: str, tool_context: ToolContext) -> dict[str, Any]:
    """Begin tracking a new project. Idempotent - returns the existing one."""
    existing = lifecycle.load(tool_context.state)
    if existing is not None:
        return {
            "success": True,
            "created": False,
            "stage": existing.stage.value,
            "note": "A workflow already exists for this session.",
        }
    record = lifecycle.WorkflowRecord(project_ref=project_ref)
    lifecycle.save(tool_context.state, record)
    return {
        "success": True,
        "created": True,
        "project_ref": project_ref,
        "stage": record.stage.value,
        "next_action": lifecycle.NEXT_ACTION[record.stage],
    }


def advance_stage(
    target_stage: str,
    tool_context: ToolContext,
    note: str = "",
    idempotency_key: str = "",
    dataset_ref: str = "",
    plan_ref: str = "",
    plan_digest: str = "",
    approval_ref: str = "",
    job_ref: str = "",
    model_ref: str = "",
    report_ref: str = "",
) -> dict[str, Any]:
    """Move the workflow to a new stage, recording why and what it produced.

    Pass whichever refs the completed stage produced; they are stored on the
    record so a later turn can use them without re-deriving anything.

    Supply an `idempotency_key` for anything that must not happen twice (above
    all, launching a job): replaying the same key is a no-op rather than a
    second launch.
    """
    record = lifecycle.load(tool_context.state)
    if record is None:
        return {"success": False, "error": "No workflow yet - call start_workflow."}

    try:
        target = lifecycle.Stage(target_stage)
    except ValueError:
        return {
            "success": False,
            "error": f"Unknown stage {target_stage!r}. Valid stages: "
                     f"{', '.join(s.value for s in lifecycle.Stage)}.",
        }

    refs = {
        k: v for k, v in {
            "dataset_ref": dataset_ref, "plan_ref": plan_ref,
            "plan_digest": plan_digest, "approval_ref": approval_ref,
            "job_ref": job_ref, "model_ref": model_ref, "report_ref": report_ref,
        }.items() if v
    }

    try:
        record.advance(
            target, note=note, idempotency_key=idempotency_key or None, **refs
        )
    except lifecycle.IllegalTransition as exc:
        return {
            "success": False,
            "error": str(exc),
            "current_stage": record.stage.value,
            "note": "Check get_workflow for the allowed transitions.",
        }

    lifecycle.save(tool_context.state, record)
    return {
        "success": True,
        "stage": record.stage.value,
        "next_action": lifecycle.NEXT_ACTION.get(record.stage, "done"),
        "is_terminal": record.is_terminal,
    }


ORCHESTRATOR_TOOLS = [
    # delegation
    list_agents,
    dispatch_task,
    get_task,
    # lifecycle
    get_workflow,
    start_workflow,
    advance_stage,
    # governance - only the orchestrator issues approvals
    request_approval,
    grant_approval,
    deny_approval,
    list_audit,
]

__all__ = [
    "list_agents",
    "dispatch_task",
    "get_task",
    "get_workflow",
    "start_workflow",
    "advance_stage",
    "ORCHESTRATOR_TOOLS",
]

