"""The whole vertical slice through the real tool functions, no LLM.

This is what one full project run does, minus the orchestrator's reasoning:
DATA -> PLAN -> approval -> TRAIN (submit, end the turn, poll later) -> EVAL,
with the lifecycle record advancing at each step and the audit trail recording
the approval sequence.

It is one test on purpose - the value is that the pieces compose, and the refs
that one stage produces are the ones the next stage consumes.
"""

from __future__ import annotations

import time

from augur_agents import lifecycle as L
from augur_agents.contracts import ParallelismConfig, TrainingPlan
from augur_agents.tools import _stubstore
from augur_agents.tools import dataset_tools as D
from augur_agents.tools import evaluation_tools as E
from augur_agents.tools import governance_tools as G
from augur_agents.tools import training_tools as T


def test_project_runs_from_objective_to_evaluation_report(monkeypatch):
    monkeypatch.setattr("augur_agents.config.STUB_TRAINING_DURATION_SECONDS", 1)
    wf = L.WorkflowRecord(project_ref="proj_e2e")

    # --- DATA ---------------------------------------------------------------
    wf.advance(L.Stage.DATA_PREPARING)
    assert D.validate_dataset("wikitext-2-raw-v1")["passed"] is True
    manifest = D.build_manifest("wikitext-2-raw-v1")
    dataset_ref = manifest["dataset_ref"]
    wf.advance(L.Stage.DATA_READY, dataset_ref=dataset_ref)

    # --- PLAN -------------------------------------------------------------- -
    wf.advance(L.Stage.PLAN_BUILDING)
    rec = T.recommend_parallelism(param_count_b=0.124, gpu_count=1,
                                  hidden_size=768, num_layers=12)
    assert rec["runnable_today"] is True
    plan = TrainingPlan(
        project_ref="proj_e2e", dataset_ref=dataset_ref, base_model="gpt2",
        param_count_b=0.124, hidden_size=768, num_layers=12, num_heads=12,
        parallelism=ParallelismConfig(**rec["parallelism"]),
    )
    plan_dict = plan.model_dump(mode="json")
    est = T.estimate_training_job(plan_dict)["estimate"]
    assert est["fits"] is True
    wf.advance(L.Stage.PLAN_READY, plan_ref=plan.id, plan_digest=plan.digest())

    # --- APPROVAL ---------------------------------------------------------- -
    wf.advance(L.Stage.AWAITING_TRAINING_APPROVAL)
    # the gate holds before approval
    assert T.submit_training_job(plan_dict)["needs_approval"] is True
    approval = G.request_approval(
        "submit_training_job", {"plan_digest": plan.digest()},
        summary="gpt2 / wikitext-2 / 1 GPU", estimate=est,
    )
    G.grant_approval(approval["approval_token"])

    # --- TRAIN: submit returns immediately, poll on a later "turn" --------- -
    started = time.monotonic()
    sub = T.submit_training_job(plan_dict, approval_token=approval["approval_token"])
    assert time.monotonic() - started < 1.5
    assert sub["state"] == "QUEUED"
    wf.advance(L.Stage.TRAINING_QUEUED, idempotency_key="launch-1", job_ref=sub["job_id"])

    status = {}
    for _ in range(8):
        time.sleep(0.4)
        status = T.get_training_status(sub["job_id"])
        if status["is_terminal"]:
            break
    assert status["state"] == "COMPLETED"
    wf.advance(L.Stage.MODEL_READY, model_ref=status["artifact_ref"])

    # the artifact links back to the exact plan that was approved
    artifact = T.get_model_artifact(status["artifact_ref"])["artifact"]
    assert artifact["lineage"]["plan_digest"] == plan.digest()
    assert artifact["lineage"]["dataset_ref"] == dataset_ref

    # --- EVAL: code decides pass/fail ------------------------------------- -
    wf.advance(L.Stage.EVALUATING)
    report = E.run_evaluation(status["artifact_ref"], suite="loss_perplexity")
    assert isinstance(report["passed"], bool)
    wf.advance(L.Stage.EVALUATED, report_ref=report["report_id"])

    # --- the record and the audit trail tell the whole story ------------- -
    assert wf.is_terminal
    assert wf.stage is L.Stage.EVALUATED
    assert wf.dataset_ref == dataset_ref
    assert wf.model_ref == status["artifact_ref"]
    assert wf.report_ref == report["report_id"]

    events = [e["event"] for e in _stubstore.audit()]
    assert events == [
        "approval_requested",
        "approval_granted",
        "approval_consumed",
        "training_submitted",
        "training_completed",
    ]


def test_a_refused_approval_sends_the_project_back_to_planning(monkeypatch):
    wf = L.WorkflowRecord(project_ref="proj_e2e", stage=L.Stage.AWAITING_TRAINING_APPROVAL)
    approval = G.request_approval("submit_training_job", {"plan_digest": "d"})
    G.deny_approval(approval["approval_token"], reason="too expensive")

    # the denied token can never launch anything
    assert not G.check_policy(
        "submit_training_job", {"plan_digest": "d"}, approval["approval_token"]
    )["allowed"]

    wf.advance(L.Stage.PLAN_BUILDING, note="user wants a cheaper plan")
    assert wf.stage is L.Stage.PLAN_BUILDING

