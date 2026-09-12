"""The stub tools: happy paths, failure paths, and the two properties that
are real rather than simulated (submit does not block; a job survives a
restart)."""

from __future__ import annotations

import time

import pytest

from augur_agents.tools import _stubstore
from augur_agents.tools import dataset_tools as D
from augur_agents.tools import evaluation_tools as E
from augur_agents.tools import research_tools as R
from augur_agents.tools import training_tools as T

## =============================================================================
# Research
## =============================================================================


class TestResearch:
    def test_search_ranks_relevant_papers_first(self):
        results = R.search_papers("memory efficient fine tuning on one GPU")["results"]
        assert results, "should find something"
        assert results[0]["arxiv_id"] == "2305.14314"  # QLoRA

    def test_a_no_match_query_returns_nothing_and_says_so(self):
        """The one failure mode that matters: never invent a citation."""
        out = R.search_papers("quantum blockchain crypto recipes")
        assert out["count"] == 0
        assert "not" in out["note"].lower()

    def test_since_filters_by_date(self):
        recent = R.search_papers("attention", since="2022-01-01")["results"]
        assert all(p["date"] >= "2022-01-01" for p in recent)

    def test_get_paper_returns_sections_for_a_known_id(self):
        out = R.get_paper("1910.02054")  # ZeRO
        assert out["success"]
        assert out["paper"]["sections"]

    def test_get_paper_rejects_an_unknown_id_but_lists_the_valid_ones(self):
        out = R.get_paper("0000.00000")
        assert not out["success"]
        assert "1910.02054" in out["error"]

    def test_summarize_returns_evidence_with_sources_not_prose(self):
        out = R.summarize_findings(["1910.02054", "2106.09685"], "cut optimizer memory")
        assert out["success"]
        assert len(out["evidence"]) == 2
        assert out["sources"] and all("arXiv:" in s for s in out["sources"])

    def test_summarize_reports_ids_it_could_not_find(self):
        out = R.summarize_findings(["1910.02054", "9999.99999"], "q")
        assert out["not_found"] == ["9999.99999"]


## =============================================================================
# Dataset
## =============================================================================


class TestDataset:
    def test_inspect_an_allow_listed_dataset(self):
        out = D.inspect_dataset("wikitext-2-raw-v1")
        assert out["success"]
        assert out["total_tokens"] > 0
        assert out["checksum"]

    def test_inspect_an_unknown_source_fails_with_the_allow_list(self):
        out = D.inspect_dataset("my-private-dataset")
        assert not out["success"]
        assert "allow-list" in out["error"]

    def test_validate_flags_a_restrictive_licence_as_blocking(self):
        out = D.validate_dataset("ag_news")
        assert out["passed"] is False
        assert any("licen" in f.lower() for f in out["findings"])

    def test_validate_passes_a_clean_dataset(self):
        out = D.validate_dataset("wikitext-2-raw-v1")
        assert out["passed"] is True

    def test_materialize_without_approval_is_refused(self):
        out = D.materialize_dataset("wikitext-2-raw-v1")
        assert not out["success"]
        assert out["needs_approval"]
        assert out["params"] == {"source": "wikitext", "revision": "wikitext-2-raw-v1"}

    def test_materialize_with_a_matching_approval_succeeds(self, approved):
        params = {"source": "wikitext", "revision": "wikitext-2-raw-v1"}
        token = approved("materialize_dataset", params)
        out = D.materialize_dataset("wikitext-2-raw-v1", approval_token=token)
        assert out["success"]
        assert out["storage_uri"].startswith("s3://")

    def test_build_manifest_produces_a_referenceable_contract(self):
        out = D.build_manifest("wikitext-2-raw-v1")
        assert out["success"]
        assert out["dataset_ref"].startswith("ds_")
        assert out["manifest"]["checksum"]


## =============================================================================
# Training - planning
## =============================================================================


@pytest.fixture
def runnable_plan(sample_plan):
    return sample_plan.model_dump(mode="json")


class TestTrainingPlanning:
    def test_recommend_parallelism_explains_every_choice(self):
        out = T.recommend_parallelism(param_count_b=0.124, gpu_count=1)
        assert out["success"]
        assert out["rationale"], "a recommendation with no reasons is not useful"
        assert out["runnable_today"] is True

    def test_estimate_returns_a_cost_with_its_assumptions(self, runnable_plan):
        out = T.estimate_training_job(runnable_plan)
        assert out["success"]
        assert out["estimate"]["estimated_cost_usd"] >= 0
        assert out["estimate"]["assumptions"]

    def test_validate_flags_a_plan_that_needs_an_unsupported_backend(self, sample_plan):
        sample_plan.parallelism.tp = 4
        sample_plan.parallelism.dp = 1
        sample_plan.resources.gpu_count = 4
        out = T.validate_training_plan(sample_plan.model_dump(mode="json"))
        assert out["backend_gaps"]
        assert out["runnable_today"] is False


## =============================================================================
# Training - submit does not block
## =============================================================================


class TestSubmitDoesNotBlock:
    def test_submit_returns_before_the_run_finishes(
        self, monkeypatch, runnable_plan, approved, sample_plan
    ):
        monkeypatch.setattr(
            "augur_agents.config.STUB_TRAINING_DURATION_SECONDS", 30
        )
        token = approved("submit_training_job", {"plan_digest": sample_plan.digest()})

        started = time.monotonic()
        out = T.submit_training_job(runnable_plan, approval_token=token)
        elapsed = time.monotonic() - started

        assert out["success"]
        assert out["state"] == "QUEUED"
        assert elapsed < 2.0, "submit must not wait for a 30s job"

    def test_submit_without_approval_is_refused(self, runnable_plan):
        out = T.submit_training_job(runnable_plan)
        assert not out["success"]
        assert out["needs_approval"]

    def test_an_approval_for_a_different_plan_does_not_work(
        self, runnable_plan, approved
    ):
        token = approved("submit_training_job", {"plan_digest": "some-other-digest"})
        out = T.submit_training_job(runnable_plan, approval_token=token)
        assert not out["success"]

    def test_a_plan_the_backend_cannot_run_is_refused_even_with_approval(
        self, sample_plan, approved
    ):
        sample_plan.parallelism.tp = 2
        sample_plan.parallelism.dp = 1
        sample_plan.resources.gpu_count = 2
        d = sample_plan.model_dump(mode="json")
        token = approved("submit_training_job", {"plan_digest": sample_plan.digest()})
        out = T.submit_training_job(d, approval_token=token)
        assert not out["success"]
        assert "backend_gaps" in out


## =============================================================================
# Training - job lifecycle
## =============================================================================


def _launch(monkeypatch, sample_plan, approved, seconds=1):
    monkeypatch.setattr(
        "augur_agents.config.STUB_TRAINING_DURATION_SECONDS", seconds
    )
    token = approved("submit_training_job", {"plan_digest": sample_plan.digest()})
    return T.submit_training_job(
        sample_plan.model_dump(mode="json"), approval_token=token
    )["job_id"]


class TestJobLifecycle:
    def test_a_job_advances_to_completed_over_wall_clock(
        self, monkeypatch, sample_plan, approved
    ):
        job = _launch(monkeypatch, sample_plan, approved, seconds=1)
        assert T.get_training_status(job)["state"] in {"QUEUED", "RUNNING"}
        time.sleep(1.3)
        done = T.get_training_status(job)
        assert done["state"] == "COMPLETED"
        assert done["artifact_ref"]

    def test_a_completed_job_registers_an_artifact_with_lineage(
        self, monkeypatch, sample_plan, approved
    ):
        job = _launch(monkeypatch, sample_plan, approved, seconds=1)
        time.sleep(1.3)
        ref = T.get_training_status(job)["artifact_ref"]
        art = T.get_model_artifact(ref)["artifact"]
        assert art["lineage"]["plan_digest"] == sample_plan.digest()

    def test_cancelling_a_queued_job_needs_no_approval(
        self, monkeypatch, sample_plan, approved
    ):
        job = _launch(monkeypatch, sample_plan, approved, seconds=30)
        out = T.cancel_training_job(job)
        assert out["success"]
        assert out["state"] == "CANCELED"

    def test_status_of_an_unknown_job_fails_cleanly(self):
        out = T.get_training_status("tj_nonexistent")
        assert not out["success"]

    def test_the_loss_curve_decreases(self, monkeypatch, sample_plan, approved):
        job = _launch(monkeypatch, sample_plan, approved, seconds=1)
        time.sleep(0.5)
        mid = T.get_training_status(job)["metrics"].get("train_loss")
        time.sleep(1.0)
        end = T.get_training_status(job)["metrics"].get("train_loss")
        if mid is not None and end is not None:
            assert end < mid


class TestJobSurvivesRestart:
    """The property the whole long-running design rests on."""

    def test_a_submitted_job_completes_after_the_store_is_reopened(
        self, monkeypatch, sample_plan, approved, tmp_path
    ):
        db = str(tmp_path / "jobs.db")
        _stubstore.reset_job_store(db)
        monkeypatch.setattr("augur_agents.config.STUB_TRAINING_DURATION_SECONDS", 1)

        token = approved("submit_training_job", {"plan_digest": sample_plan.digest()})
        job = T.submit_training_job(
            sample_plan.model_dump(mode="json"), approval_token=token
        )["job_id"]

        # Simulate a worker restart: throw away the store object, reopen the file.
        _stubstore.job_store().close()
        _stubstore._job_store = _stubstore.JobStore(db)

        time.sleep(1.3)
        out = T.get_training_status(job)
        assert out["success"]
        assert out["state"] == "COMPLETED"


## =============================================================================
# Evaluation - code decides pass/fail
## =============================================================================


class TestEvaluation:
    def test_run_evaluation_reports_per_metric_pass_fail(self):
        out = E.run_evaluation("model_abc", suite="loss_perplexity")
        assert out["success"]
        judged = [m for m in out["metrics"] if m["threshold"] is not None]
        assert judged
        assert all(isinstance(m["passed"], bool) for m in judged)

    def test_results_are_deterministic_for_the_same_artifact(self):
        a = E.run_evaluation("model_xyz")["metrics"]
        b = E.run_evaluation("model_xyz")["metrics"]
        assert [m["value"] for m in a] == [m["value"] for m in b]

    def test_an_unknown_suite_is_refused(self):
        out = E.run_evaluation("model_abc", suite="made-up")
        assert not out["success"]

    def test_custom_thresholds_override_the_defaults(self):
        strict = E.run_evaluation("model_abc", thresholds={"eval_loss": 0.0})
        loss = next(m for m in strict["metrics"] if m["name"] == "eval_loss")
        assert loss["passed"] is False

    def test_compare_refuses_reports_from_different_suites(self):
        r1 = E.run_evaluation("m1", suite="loss_perplexity")["report_id"]
        r2 = E.run_evaluation("m2", suite="throughput")["report_id"]
        out = E.compare_candidates([r1, r2])
        assert not out["success"]
        assert "suite" in out["error"].lower()

    def test_compare_ranks_within_a_suite(self):
        r1 = E.run_evaluation("cand-a", suite="loss_perplexity")["report_id"]
        r2 = E.run_evaluation("cand-b", suite="loss_perplexity")["report_id"]
        out = E.compare_candidates([r1, r2], primary_metric="perplexity")
        assert out["success"]
        # lower perplexity is better
        assert out["ranking"][0]["perplexity"] <= out["ranking"][1]["perplexity"]

    def test_compare_needs_at_least_two_reports(self):
        r1 = E.run_evaluation("m1")["report_id"]
        assert not E.compare_candidates([r1])["success"]

