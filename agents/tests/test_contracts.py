"""Contracts, and the digest semantics approvals depend on."""

from __future__ import annotations

import pytest

from augur_agents.contracts import (
    ApprovalRequest,
    DataQualityReport,
    DatasetManifest,
    DatasetSplit,
    EvaluationReport,
    MarketSnapshot,
    MetricResult,
    ModelArtifact,
    ParallelismConfig,
    ProjectSpec,
    TradeDecision,
    TrainingEstimate,
    TrainingJob,
    TrainingPlan,
    canonical_json,
    digest_of,
)


def test_every_contract_round_trips_through_json():
    """A contract must survive being sent over the wire and reloaded."""
    items = [
        ProjectSpec(objective="train a small LM", base_model="gpt2"),
        DatasetManifest(
            source="wikitext", revision="wikitext-2-raw-v1", license="cc-by-sa-3.0",
            splits=[DatasetSplit(name="train", num_rows=10, num_tokens=100)],
            checksum="abc", storage_uri="s3://bucket/x/",
        ),
        TrainingPlan(project_ref="p", dataset_ref="d", base_model="gpt2"),
        TrainingJob(plan_ref="plan_1", plan_digest="abc"),
        ModelArtifact(job_ref="tj_1", checkpoint_uri="s3://x/", checksum="c",
                      base_model="gpt2"),
        EvaluationReport(model_ref="m", suite="loss_perplexity"),
        ApprovalRequest(action="submit_training_job", action_digest="abc"),
    ]
    for original in items:
        restored = type(original).model_validate_json(original.model_dump_json())
        assert restored == original, type(original).__name__


def test_canonical_json_is_key_order_independent():
    """Two structurally equal payloads must hash identically."""
    assert canonical_json({"b": 1, "a": 2}) == canonical_json({"a": 2, "b": 1})
    assert digest_of({"x": [1, 2]}) == digest_of({"x": [1, 2]})


class TestTrainingPlanDigest:
    """The digest is what an approval binds to, so its boundaries matter."""

    def test_stable_across_round_trip(self, sample_plan):
        reloaded = TrainingPlan.model_validate_json(sample_plan.model_dump_json())
        assert reloaded.digest() == sample_plan.digest()

    @pytest.mark.parametrize(
        "mutate",
        [
            pytest.param(lambda p: setattr(p.resources, "gpu_count", 64), id="gpu_count"),
            pytest.param(lambda p: setattr(p.parallelism, "tp", 8), id="tensor_parallel"),
            pytest.param(lambda p: setattr(p, "base_model", "llama-7b"), id="base_model"),
            pytest.param(lambda p: setattr(p, "dataset_ref", "ds_other"), id="dataset"),
            pytest.param(lambda p: setattr(p.parallelism, "gbs", 4096), id="batch_size"),
            pytest.param(lambda p: setattr(p, "learning_rate", 0.1), id="learning_rate"),
        ],
    )
    def test_changing_what_runs_invalidates_the_digest(self, sample_plan, mutate):
        """Anything that changes the actual run must change the digest.

        This is the property that stops an approval for a 1-GPU run being spent
        on a 64-GPU one.
        """
        before = sample_plan.digest()
        mutate(sample_plan)
        assert sample_plan.digest() != before

    def test_estimate_and_provenance_do_not_affect_it(self, sample_plan):
        """An estimate is a prediction *about* a plan, not part of it.

        If it counted, attaching a cost estimate would invalidate the approval
        the user just gave for that very cost.
        """
        before = sample_plan.digest()
        sample_plan.estimate = TrainingEstimate(
            peak_vram_gb_per_gpu=4.0, fits=True, total_flops=1e15,
            estimated_hours=0.5, estimated_cost_usd=1.0,
        )
        sample_plan.provenance = {"produced_by": "training_agent"}
        assert sample_plan.digest() == before


def test_training_job_terminality():
    job = TrainingJob(plan_ref="p", plan_digest="d")
    assert not job.is_terminal
    for state in ("COMPLETED", "FAILED", "CANCELED"):
        job.state = state
        assert job.is_terminal


def test_parallelism_world_size():
    par = ParallelismConfig(dp=4, tp=2, pp=2, cp=1)
    assert par.world_size == 16


class TestEvaluationReportVerdict:
    def test_passes_only_when_every_judged_metric_passes(self):
        report = EvaluationReport(
            model_ref="m", suite="s",
            metrics=[
                MetricResult(name="a", value=1.0, threshold=2.0, passed=True),
                MetricResult(name="b", value=3.0, threshold=2.0, passed=False),
            ],
        )
        assert report.passed is False

    def test_unjudged_metrics_are_ignored(self):
        report = EvaluationReport(
            model_ref="m", suite="s",
            metrics=[
                MetricResult(name="a", value=1.0, threshold=2.0, passed=True),
                MetricResult(name="b", value=3.0),  # no threshold
            ],
        )
        assert report.passed is True

    def test_no_thresholds_at_all_is_undecided_not_a_pass(self):
        report = EvaluationReport(
            model_ref="m", suite="s", metrics=[MetricResult(name="a", value=1.0)]
        )
        assert report.passed is None


class TestApprovalSpendability:
    def test_granted_and_unexpired_is_spendable(self):
        assert ApprovalRequest(
            action="a", action_digest="d", granted=True
        ).is_spendable()

    def test_ungranted_consumed_or_expired_are_not(self):
        from datetime import datetime, timedelta, timezone

        assert not ApprovalRequest(action="a", action_digest="d").is_spendable()
        assert not ApprovalRequest(
            action="a", action_digest="d", granted=True, consumed=True
        ).is_spendable()
        assert not ApprovalRequest(
            action="a", action_digest="d", granted=True,
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        ).is_spendable()


class TestTradingFoundation:
    def test_market_snapshot_marks_stale_data(self):
        from datetime import datetime, timedelta, timezone

        stale = MarketSnapshot(
            asset="BTC/USD",
            timestamp=datetime.now(timezone.utc) - timedelta(seconds=30),
            price=50000.0,
            ohlcv={"15m": {"open": 49900.0, "high": 50200.0, "low": 49850.0, "close": 50000.0, "volume": 12.0}, "1h": {"open": 49500.0, "high": 50350.0, "low": 49400.0, "close": 50000.0, "volume": 40.0}, "4h": {"open": 49000.0, "high": 50700.0, "low": 48800.0, "close": 50000.0, "volume": 100.0}, "1d": {"open": 47000.0, "high": 51000.0, "low": 46500.0, "close": 50000.0, "volume": 300.0}},
            volume=120.0,
            spread=0.001,
            liquidity=0.86,
            volatility={"atr": 420.0, "realized_volatility": 0.045},
            derivatives={"funding_rate": 0.0001, "open_interest": 2.1, "basis": 0.002, "liquidation_data": {"shorts": 500, "longs": 450}},
        )

        assert stale.is_fresh(max_age_seconds=10) is False
        assert stale.data_quality().quality_score < 1.0

    def test_trade_decision_validates_signal_and_bounds(self):
        decision = TradeDecision(
            decision="NO_TRADE",
            confidence=0.35,
            evidence_quality=0.65,
            data_quality=0.55,
            reason="Insufficient conviction after conflict checks.",
        )
        assert decision.decision == "NO_TRADE"

        with pytest.raises(ValueError):
            TradeDecision(
                decision="BUY",
                confidence=1.7,
                evidence_quality=0.4,
                data_quality=0.5,
                reason="Bad confidence.",
            )

    def test_data_quality_report_tracks_missing_fields(self):
        report = DataQualityReport(
            source="binance",
            timestamp="2026-09-12T00:00:00Z",
            latency_ms=400,
            freshness=0.25,
            quality_score=0.7,
            missing_fields=["liquidity"],
            anomalies=["volatility spike"],
        )

        assert report.missing_fields == ["liquidity"]
        assert report.quality_score == pytest.approx(0.7)

