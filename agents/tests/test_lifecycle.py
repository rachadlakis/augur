"""The workflow state machine, including the properties long runs depend on."""

from __future__ import annotations

import json

import pytest

from augur_agents.lifecycle import (
    NEXT_ACTION,
    TERMINAL_STAGES,
    IllegalTransition,
    Stage,
    WorkflowRecord,
    load,
    save,
)

HAPPY_PATH = [
    Stage.DATA_PREPARING,
    Stage.DATA_READY,
    Stage.PLAN_BUILDING,
    Stage.PLAN_READY,
    Stage.AWAITING_TRAINING_APPROVAL,
    Stage.TRAINING_QUEUED,
    Stage.TRAINING_RUNNING,
    Stage.MODEL_READY,
    Stage.EVALUATING,
    Stage.EVALUATED,
]


def test_the_whole_happy_path_is_legal():
    record = WorkflowRecord(project_ref="p")
    for stage in HAPPY_PATH:
        record.advance(stage)
    assert record.stage is Stage.EVALUATED
    assert record.is_terminal
    assert len(record.audit) == len(HAPPY_PATH)


def test_a_fast_job_may_skip_the_running_stage():
    """A job can finish between two polls; requiring RUNNING would strand it."""
    record = WorkflowRecord(project_ref="p")
    for stage in HAPPY_PATH[:6]:  # ... -> TRAINING_QUEUED
        record.advance(stage)
    record.advance(Stage.MODEL_READY)
    assert record.stage is Stage.MODEL_READY


def test_illegal_transitions_are_refused():
    record = WorkflowRecord(project_ref="p")
    with pytest.raises(IllegalTransition, match="cannot go DRAFT -> EVALUATED"):
        record.advance(Stage.EVALUATED)
    assert record.stage is Stage.DRAFT, "a refused transition must not mutate"


@pytest.mark.parametrize("terminal", sorted(TERMINAL_STAGES, key=lambda s: s.value))
def test_terminal_stages_accept_nothing(terminal):
    record = WorkflowRecord(project_ref="p", stage=terminal)
    with pytest.raises(IllegalTransition):
        record.advance(Stage.DATA_PREPARING)


def test_off_ramps_are_reachable_from_a_running_job():
    record = WorkflowRecord(project_ref="p", stage=Stage.TRAINING_RUNNING)
    record.advance(Stage.FAILED, note="worker crashed")
    assert record.stage is Stage.FAILED


def test_a_refused_approval_sends_the_plan_back():
    record = WorkflowRecord(project_ref="p", stage=Stage.AWAITING_TRAINING_APPROVAL)
    record.advance(Stage.PLAN_BUILDING, note="user asked for fewer GPUs")
    assert record.stage is Stage.PLAN_BUILDING


class TestIdempotency:
    """A retried command must not launch a second paid job."""

    def test_replaying_a_key_is_a_no_op(self):
        record = WorkflowRecord(project_ref="p", stage=Stage.AWAITING_TRAINING_APPROVAL)
        record.advance(Stage.TRAINING_QUEUED, idempotency_key="launch-1", job_ref="tj_1")
        audit_len = len(record.audit)

        record.advance(
            Stage.TRAINING_QUEUED, idempotency_key="launch-1", job_ref="tj_DUPLICATE"
        )

        assert record.job_ref == "tj_1", "the replay must not overwrite the real job"
        assert len(record.audit) == audit_len, "the replay must not be audited twice"

    def test_a_different_key_is_a_real_transition(self):
        record = WorkflowRecord(project_ref="p", stage=Stage.TRAINING_QUEUED)
        record.advance(Stage.TRAINING_RUNNING, idempotency_key="k2")
        assert record.stage is Stage.TRAINING_RUNNING


class TestPersistence:
    """What makes a run survive the end of a turn, and the process."""

    def test_record_round_trips_through_json_session_state(self):
        record = WorkflowRecord(project_ref="p")
        record.advance(Stage.DATA_PREPARING)
        record.advance(Stage.DATA_READY, dataset_ref="ds_1")
        record.set_pending(agent="training", task_id="task-99", description="run")

        state: dict = {}
        save(state, record)
        json.dumps(state)  # must be JSON-safe for DatabaseSessionService

        restored = load(state)
        assert restored is not None
        assert restored.stage is Stage.DATA_READY
        assert restored.dataset_ref == "ds_1"
        assert restored.pending is not None
        assert restored.pending.agent == "training"
        assert restored.pending.task_id == "task-99"

    def test_missing_state_loads_as_none(self):
        assert load({}) is None

    def test_advancing_clears_the_pending_task(self):
        record = WorkflowRecord(project_ref="p", stage=Stage.TRAINING_RUNNING)
        record.set_pending(agent="training", task_id="t1")
        record.advance(Stage.MODEL_READY, model_ref="m1")
        assert record.pending is None


def test_unknown_ref_field_is_rejected():
    record = WorkflowRecord(project_ref="p")
    with pytest.raises(AttributeError, match="no field"):
        record.advance(Stage.DATA_PREPARING, not_a_field="x")


def test_every_stage_has_a_next_action():
    for stage in Stage:
        assert stage in NEXT_ACTION, f"{stage} has no next action"

