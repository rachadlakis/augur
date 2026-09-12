"""The workflow state machine.

The pipeline is an explicit state machine, not something the orchestrator LLM is
trusted to remember. That matters for two reasons:

* **Long runs.** A training job can take hours or days. The orchestrator ends its
  turn while the job runs, so on the next turn the *record* - not the model's
  context - is what says where we are and which A2A task to poll.
* **Auditability.** Every transition is a typed command with an idempotency key
  and an audit entry, so "why did this run get approved and launched" has an
  answer that does not depend on a chat transcript.

The record is plain JSON so it can live in ADK session state and be persisted by
``DatabaseSessionService``. A dedicated workflow store replaces this in
IMPLEMENTATION_PLAN Phase 1; the shape here is deliberately close to what that
store will hold.

Research is intentionally absent from this machine: it is advisory, can be
consulted at any point, and never gates a stage.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Stage(str, Enum):
    DRAFT = "DRAFT"
    DATA_PREPARING = "DATA_PREPARING"
    DATA_READY = "DATA_READY"
    PLAN_BUILDING = "PLAN_BUILDING"
    PLAN_READY = "PLAN_READY"
    AWAITING_TRAINING_APPROVAL = "AWAITING_TRAINING_APPROVAL"
    TRAINING_QUEUED = "TRAINING_QUEUED"
    TRAINING_RUNNING = "TRAINING_RUNNING"
    MODEL_READY = "MODEL_READY"
    EVALUATING = "EVALUATING"
    EVALUATED = "EVALUATED"
    # Terminal / off-ramp states
    BLOCKED = "BLOCKED"
    CANCELED = "CANCELED"
    FAILED = "FAILED"


TERMINAL_STAGES: frozenset[Stage] = frozenset(
    {Stage.EVALUATED, Stage.CANCELED, Stage.FAILED}
)

# Any non-terminal stage may go to these: things go wrong everywhere.
_OFF_RAMPS: frozenset[Stage] = frozenset({Stage.BLOCKED, Stage.CANCELED, Stage.FAILED})

# The happy path. Off-ramps are added to every source below.
_FORWARD: dict[Stage, frozenset[Stage]] = {
    Stage.DRAFT: frozenset({Stage.DATA_PREPARING}),
    Stage.DATA_PREPARING: frozenset({Stage.DATA_READY}),
    Stage.DATA_READY: frozenset({Stage.PLAN_BUILDING}),
    Stage.PLAN_BUILDING: frozenset({Stage.PLAN_READY}),
    Stage.PLAN_READY: frozenset({Stage.AWAITING_TRAINING_APPROVAL}),
    # An approval can be refused, which sends the plan back to be rebuilt.
    Stage.AWAITING_TRAINING_APPROVAL: frozenset(
        {Stage.TRAINING_QUEUED, Stage.PLAN_BUILDING}
    ),
    Stage.TRAINING_QUEUED: frozenset({Stage.TRAINING_RUNNING}),
    # A job may finish between two polls, so QUEUED/RUNNING -> MODEL_READY both
    # need to be legal; insisting on observing RUNNING would strand fast jobs.
    Stage.TRAINING_RUNNING: frozenset({Stage.MODEL_READY}),
    Stage.MODEL_READY: frozenset({Stage.EVALUATING}),
    Stage.EVALUATING: frozenset({Stage.EVALUATED}),
    # A blocked run can be picked back up once whatever blocked it is resolved.
    Stage.BLOCKED: frozenset({Stage.PLAN_BUILDING, Stage.DATA_PREPARING}),
}
_FORWARD[Stage.TRAINING_QUEUED] = _FORWARD[Stage.TRAINING_QUEUED] | {Stage.MODEL_READY}

TRANSITIONS: dict[Stage, frozenset[Stage]] = {
    stage: (targets | _OFF_RAMPS) - {stage}
    for stage, targets in _FORWARD.items()
}
for _terminal in TERMINAL_STAGES:
    TRANSITIONS.setdefault(_terminal, frozenset())


class IllegalTransition(RuntimeError):
    """Raised when a transition is not allowed from the current stage."""


class AuditEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    at: str = Field(default_factory=_now_iso)
    from_stage: Stage
    to_stage: Stage
    note: str = ""
    idempotency_key: str | None = None
    actor: str = "orchestrator"


class PendingTask(BaseModel):
    """The A2A task this workflow is currently waiting on.

    This is what makes a multi-hour delegation survivable: the orchestrator
    stores the worker and task id here, ends its turn, and a later turn polls
    ``get_task`` instead of trying to hold a call open.
    """

    model_config = ConfigDict(extra="forbid")

    agent: str
    task_id: str
    context_id: str | None = None
    stage: Stage
    dispatched_at: str = Field(default_factory=_now_iso)
    description: str = ""


class WorkflowRecord(BaseModel):
    """Durable state of one project's run through the pipeline."""

    model_config = ConfigDict(extra="forbid")

    project_ref: str
    stage: Stage = Stage.DRAFT

    # Artifact references produced along the way. Strings, not objects: the
    # payloads live with whichever agent produced them.
    dataset_ref: str | None = None
    plan_ref: str | None = None
    plan_digest: str | None = None
    approval_ref: str | None = None
    job_ref: str | None = None
    model_ref: str | None = None
    report_ref: str | None = None

    pending: PendingTask | None = None
    attempts: dict[str, int] = Field(default_factory=dict)
    audit: list[AuditEntry] = Field(default_factory=list)
    # Keys of transitions already applied, so a retried command is a no-op
    # rather than a second launch.
    applied_keys: list[str] = Field(default_factory=list)

    @property
    def is_terminal(self) -> bool:
        return self.stage in TERMINAL_STAGES

    def can_advance_to(self, target: Stage) -> bool:
        return target in TRANSITIONS.get(self.stage, frozenset())

    def advance(
        self,
        target: Stage,
        *,
        note: str = "",
        idempotency_key: str | None = None,
        actor: str = "orchestrator",
        **refs: Any,
    ) -> WorkflowRecord:
        """Move to ``target``, recording an audit entry. Mutates in place.

        Replaying the same ``idempotency_key`` is a no-op - the guard that stops
        a retried "launch the job" command from launching a second paid job.
        """
        if idempotency_key and idempotency_key in self.applied_keys:
            return self

        if not self.can_advance_to(target):
            allowed = ", ".join(sorted(s.value for s in TRANSITIONS.get(self.stage, ())))
            raise IllegalTransition(
                f"cannot go {self.stage.value} -> {target.value}; "
                f"allowed from {self.stage.value}: {allowed or '(terminal)'}"
            )

        for key, value in refs.items():
            if not hasattr(self, key):
                raise AttributeError(f"WorkflowRecord has no field {key!r}")
            setattr(self, key, value)

        self.audit.append(
            AuditEntry(
                from_stage=self.stage,
                to_stage=target,
                note=note,
                idempotency_key=idempotency_key,
                actor=actor,
            )
        )
        self.attempts[target.value] = self.attempts.get(target.value, 0) + 1
        self.stage = target
        if idempotency_key:
            self.applied_keys.append(idempotency_key)
        # Arriving at a new stage clears whatever we were waiting on.
        self.pending = None
        return self

    def set_pending(
        self,
        *,
        agent: str,
        task_id: str,
        context_id: str | None = None,
        description: str = "",
    ) -> PendingTask:
        """Record the A2A task this workflow is now waiting on."""
        self.pending = PendingTask(
            agent=agent,
            task_id=task_id,
            context_id=context_id,
            stage=self.stage,
            description=description,
        )
        return self.pending


## =============================================================================
# Session-state round trip
#
# ADK session state holds JSON, so the record is stored as a plain dict under
# one key. With SESSION_BACKEND=database this is what survives a restart while a
# training job runs.
## =============================================================================

STATE_KEY = "workflow"


def load(state: dict[str, Any]) -> WorkflowRecord | None:
    """Read the workflow record out of ADK session state, if there is one."""
    raw = state.get(STATE_KEY)
    if not raw:
        return None
    if isinstance(raw, WorkflowRecord):
        return raw
    return WorkflowRecord.model_validate(raw)


def save(state: dict[str, Any], record: WorkflowRecord) -> WorkflowRecord:
    """Write the record back to session state as plain JSON-safe data."""
    state[STATE_KEY] = record.model_dump(mode="json")
    return record


NextAction = Literal[
    "prepare_data", "build_plan", "request_approval",
    "launch_training", "poll_training", "evaluate", "done", "blocked",
]

# What the orchestrator should do next from each stage. The LLM still decides
# *how* (which agent, what instruction), but it never has to infer the order.
NEXT_ACTION: dict[Stage, NextAction] = {
    Stage.DRAFT: "prepare_data",
    Stage.DATA_PREPARING: "poll_training",   # generic "poll the pending task"
    Stage.DATA_READY: "build_plan",
    Stage.PLAN_BUILDING: "poll_training",
    Stage.PLAN_READY: "request_approval",
    Stage.AWAITING_TRAINING_APPROVAL: "launch_training",
    Stage.TRAINING_QUEUED: "poll_training",
    Stage.TRAINING_RUNNING: "poll_training",
    Stage.MODEL_READY: "evaluate",
    Stage.EVALUATING: "poll_training",
    Stage.EVALUATED: "done",
    Stage.BLOCKED: "blocked",
    Stage.CANCELED: "done",
    Stage.FAILED: "done",
}


__all__ = [
    "Stage",
    "TERMINAL_STAGES",
    "TRANSITIONS",
    "IllegalTransition",
    "AuditEntry",
    "PendingTask",
    "WorkflowRecord",
    "STATE_KEY",
    "load",
    "save",
    "NEXT_ACTION",
]
