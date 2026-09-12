"""The orchestrator's tools, against a fake agent directory.

Pins three things:

* routing goes through the discovered roster, not a hard-coded name;
* the workflow record is the source of truth, and a pending task survives a
  turn ending - which is how a multi-hour run is resumed;
* a delegation failure is a readable result, never an exception.
"""

from __future__ import annotations

import pytest

from augur_agents import a2a_client, lifecycle
from augur_agents.orchestrator import tools as O


class FakeDirectory:
    """Records calls and returns whatever a test tells it to."""

    def __init__(self):
        self.dispatched: list[tuple[str, str]] = []
        self.polled: list[tuple[str, str]] = []
        self._roster = [
            {"name": "data", "available": True,
             "skills": [{"id": "dataset_curation", "description": "datasets"}]},
            {"name": "training", "available": True,
             "skills": [{"id": "model_training", "description": "training"}]},
            {"name": "evaluation", "available": False, "url": "http://x",
             "error": "ConnectError: down"},
        ]
        self.dispatch_result = {
            "success": True, "state": "completed", "is_terminal": True,
            "task_id": "t-done", "context_id": "c-1", "result": "ok",
        }
        self.get_task_result = {
            "success": True, "state": "completed", "is_terminal": True,
            "task_id": "t-pending", "result": "finished",
        }

    async def list_agents(self):
        return self._roster

    async def dispatch_task(self, agent_name, instruction, *, context_id=None):
        self.dispatched.append((agent_name, instruction))
        return {**self.dispatch_result}

    async def get_task(self, agent_name, task_id):
        self.polled.append((agent_name, task_id))
        return {**self.get_task_result}


@pytest.fixture
def fake_dir(monkeypatch):
    fd = FakeDirectory()
    monkeypatch.setattr(a2a_client, "get_directory", lambda: fd)
    return fd


@pytest.fixture
def ctx(tool_context):
    return tool_context


## =============================================================================
# Routing
## =============================================================================


class TestRouting:
    async def test_list_agents_surfaces_the_roster_including_the_down_one(
        self, fake_dir, ctx
    ):
        out = await O.list_agents()
        assert out["count"] == 3
        names = {a["name"]: a["available"] for a in out["agents"]}
        assert names == {"data": True, "training": True, "evaluation": False}

    async def test_dispatch_records_the_target_and_the_instruction(self, fake_dir, ctx):
        await O.dispatch_task("data", "prepare wikitext-2", ctx)
        assert fake_dir.dispatched == [("data", "prepare wikitext-2")]

    async def test_dispatch_reuses_a_worker_context_id_across_turns(self, fake_dir, ctx):
        await O.dispatch_task("data", "first", ctx)
        assert ctx.state["context_id:data"] == "c-1"
        # a later call should thread the same context id back in
        seen = {}
        orig = fake_dir.dispatch_task

        async def spy(agent, instr, *, context_id=None):
            seen["context_id"] = context_id
            return await orig(agent, instr, context_id=context_id)

        fake_dir.dispatch_task = spy
        await O.dispatch_task("data", "second", ctx)
        assert seen["context_id"] == "c-1"


## =============================================================================
# Long-running work - the pending task outlives the turn
## =============================================================================


class TestPendingTaskSurvivesTheTurn:
    async def test_a_working_dispatch_is_recorded_on_the_workflow(self, fake_dir, ctx):
        O.start_workflow("proj_1", ctx)
        O.advance_stage("DATA_PREPARING", ctx)
        O.advance_stage("DATA_READY", ctx, dataset_ref="ds_1")
        O.advance_stage("PLAN_BUILDING", ctx)
        O.advance_stage("PLAN_READY", ctx, plan_ref="plan_1", plan_digest="dig")
        O.advance_stage("AWAITING_TRAINING_APPROVAL", ctx)
        O.advance_stage("TRAINING_QUEUED", ctx, job_ref="tj_1")
        O.advance_stage("TRAINING_RUNNING", ctx)

        fake_dir.dispatch_result = {
            "success": True, "state": "working", "is_terminal": False,
            "task_id": "t-long", "context_id": "c-1",
        }
        out = await O.dispatch_task("training", "run job tj_1", ctx, description="the run")
        assert out["state"] == "working"

        # A fresh load - as a later turn would do - still sees the pending task.
        record = lifecycle.load(ctx.state)
        assert record.pending is not None
        assert record.pending.task_id == "t-long"
        assert record.pending.agent == "training"

    async def test_get_task_clears_the_pending_task_once_it_is_terminal(
        self, fake_dir, ctx
    ):
        O.start_workflow("proj_1", ctx)
        record = lifecycle.load(ctx.state)
        record.stage = lifecycle.Stage.TRAINING_RUNNING
        record.set_pending(agent="training", task_id="t-pending")
        lifecycle.save(ctx.state, record)

        out = await O.get_task("training", "t-pending", ctx)
        assert out["is_terminal"]
        assert lifecycle.load(ctx.state).pending is None

    async def test_get_workflow_reports_the_pending_task_for_a_later_turn(
        self, fake_dir, ctx
    ):
        O.start_workflow("proj_1", ctx)
        record = lifecycle.load(ctx.state)
        record.stage = lifecycle.Stage.TRAINING_RUNNING
        record.set_pending(agent="training", task_id="t-long", description="the run")
        lifecycle.save(ctx.state, record)

        wf = O.get_workflow(ctx)
        assert wf["pending_task"]["task_id"] == "t-long"
        assert wf["stage"] == "TRAINING_RUNNING"


## =============================================================================
# The workflow is the source of truth
## =============================================================================


class TestWorkflowTool:
    def test_get_workflow_before_start_says_there_is_none(self, ctx):
        out = O.get_workflow(ctx)
        assert out["exists"] is False
        assert "start_workflow" in out["note"]

    def test_start_workflow_is_idempotent(self, ctx):
        O.start_workflow("proj_1", ctx)
        again = O.start_workflow("proj_1", ctx)
        assert again["created"] is False

    def test_advance_stage_rejects_an_illegal_jump(self, ctx):
        O.start_workflow("proj_1", ctx)
        out = O.advance_stage("EVALUATED", ctx)
        assert out["success"] is False
        assert "get_workflow" in out["note"]

    def test_advance_stage_rejects_an_unknown_stage_name(self, ctx):
        O.start_workflow("proj_1", ctx)
        out = O.advance_stage("NONSENSE", ctx)
        assert out["success"] is False

    def test_advance_stage_stores_the_refs_the_stage_produced(self, ctx):
        O.start_workflow("proj_1", ctx)
        O.advance_stage("DATA_PREPARING", ctx)
        O.advance_stage("DATA_READY", ctx, dataset_ref="ds_42")
        assert O.get_workflow(ctx)["refs"]["dataset_ref"] == "ds_42"

    def test_a_replayed_idempotency_key_does_not_double_advance(self, ctx):
        O.start_workflow("proj_1", ctx)
        O.advance_stage("DATA_PREPARING", ctx)
        O.advance_stage("DATA_READY", ctx)
        O.advance_stage("PLAN_BUILDING", ctx)
        O.advance_stage("PLAN_READY", ctx, plan_digest="d")
        O.advance_stage("AWAITING_TRAINING_APPROVAL", ctx)
        O.advance_stage("TRAINING_QUEUED", ctx, idempotency_key="launch-1", job_ref="tj_1")
        O.advance_stage("TRAINING_QUEUED", ctx, idempotency_key="launch-1", job_ref="tj_2")
        assert O.get_workflow(ctx)["refs"]["job_ref"] == "tj_1"


## =============================================================================
# Failure is data
## =============================================================================


async def test_a_failed_dispatch_is_a_dict_not_an_exception(fake_dir, ctx):
    fake_dir.dispatch_result = {
        "success": False, "error": "training is down", "agent": "training",
    }
    out = await O.dispatch_task("training", "run", ctx)
    assert out["success"] is False
    assert "down" in out["error"]


async def test_advance_stage_without_a_workflow_is_refused(ctx):
    out = O.advance_stage("DATA_PREPARING", ctx)
    assert out["success"] is False
    assert "start_workflow" in out["error"]

