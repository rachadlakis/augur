"""Benchmark execution and comparison for the Evaluation Agent (stub).

Stands in for an ``evaluation-mcp`` with pinned benchmark versions.

Two properties matter more than the numbers:

* **Thresholds decide pass/fail, not prose.** ``compare_candidates`` is ordinary
  Python. An LLM asked to judge its own model's scores is exactly the wrong
  place to put the decision, and "the loss looks good to me" is not a release
  gate.
* **Results are deterministic for a given artifact.** Metrics are derived from a
  hash of the artifact id, so re-running an evaluation returns the same numbers.
  Random results would make the comparison logic untestable and would hide
  contamination bugs behind noise.
"""

from __future__ import annotations

import hashlib
from typing import Any

from augur_agents.contracts import EvaluationReport, MetricResult
from augur_agents.tools import _stubstore

## =============================================================================
# Suites
#
# `higher_is_better` is what stops the comparison logic from silently treating a
# loss increase as an improvement.
## =============================================================================

SUITES: dict[str, dict[str, Any]] = {
    "loss_perplexity": {
        "version": "1.0.0",
        "description": "Held-out loss, perplexity and token accuracy.",
        "metrics": {
            "eval_loss": {"higher_is_better": False, "range": (1.4, 4.5)},
            "perplexity": {"higher_is_better": False, "range": (4.0, 90.0)},
            "token_accuracy": {"higher_is_better": True, "range": (0.28, 0.72)},
        },
        "num_samples": 2_000,
    },
    "generation_quality": {
        "version": "1.0.0",
        "description": "Reference-based generation scores.",
        "metrics": {
            "rouge_l": {"higher_is_better": True, "range": (0.15, 0.55)},
            "bleu": {"higher_is_better": True, "range": (0.05, 0.40)},
        },
        "num_samples": 500,
    },
    "throughput": {
        "version": "1.0.0",
        "description": "Inference latency and tokens per second.",
        "metrics": {
            "tokens_per_second": {"higher_is_better": True, "range": (40.0, 2400.0)},
            "p95_latency_ms": {"higher_is_better": False, "range": (25.0, 900.0)},
        },
        "num_samples": 200,
    },
}

# Default gates for the primary suite. Deliberately explicit rather than derived
# from the model's own output.
DEFAULT_THRESHOLDS: dict[str, float] = {
    "eval_loss": 3.0,
    "perplexity": 25.0,
    "token_accuracy": 0.35,
}

_STUB_NOTE = (
    "Stub evaluation - metrics are deterministic pseudo-values derived from the "
    "artifact id, not a real benchmark run."
)


def _value_for(artifact_ref: str, suite: str, metric: str, lo: float, hi: float) -> float:
    """A stable pseudo-value in [lo, hi] for one (artifact, suite, metric)."""
    seed = hashlib.sha256(f"{artifact_ref}|{suite}|{metric}".encode()).digest()
    frac = int.from_bytes(seed[:4], "big") / 0xFFFFFFFF
    return round(lo + frac * (hi - lo), 4)


def _passed(value: float, threshold: float, higher_is_better: bool) -> bool:
    return value >= threshold if higher_is_better else value <= threshold


def list_suites() -> dict[str, Any]:
    """Available benchmark suites and their metrics. Read-only."""
    return {
        "success": True,
        "suites": [
            {
                "name": name,
                "version": s["version"],
                "description": s["description"],
                "metrics": list(s["metrics"]),
                "num_samples": s["num_samples"],
            }
            for name, s in SUITES.items()
        ],
        "default_thresholds": DEFAULT_THRESHOLDS,
    }


def run_evaluation(
    model_artifact_ref: str,
    suite: str = "loss_perplexity",
    dataset_ref: str | None = None,
    thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Run a benchmark suite against a model artifact. Read-only.

    ``thresholds`` are applied by code here, and the per-metric ``passed`` flags
    in the report are the authority on whether the model cleared them.
    """
    spec = SUITES.get(suite)
    if spec is None:
        return {
            "success": False,
            "error": f"Unknown suite {suite!r}. Available: {', '.join(SUITES)}.",
        }
    if not model_artifact_ref:
        return {"success": False, "error": "model_artifact_ref is required."}

    gates = {**(DEFAULT_THRESHOLDS if suite == "loss_perplexity" else {}),
             **(thresholds or {})}

    metrics: list[MetricResult] = []
    for name, meta in spec["metrics"].items():
        lo, hi = meta["range"]
        value = _value_for(model_artifact_ref, suite, name, lo, hi)
        threshold = gates.get(name)
        metrics.append(
            MetricResult(
                name=name,
                value=value,
                threshold=threshold,
                passed=(
                    _passed(value, threshold, meta["higher_is_better"])
                    if threshold is not None else None
                ),
            )
        )

    report = EvaluationReport(
        model_ref=model_artifact_ref,
        suite=suite,
        suite_version=spec["version"],
        dataset_ref=dataset_ref,
        metrics=metrics,
        num_samples=spec["num_samples"],
        provenance={"produced_by": "evaluation_agent", "tool": "run_evaluation"},
    )
    _stubstore.evaluations()[report.id] = report.model_dump(mode="json")

    return {
        "success": True,
        "report_id": report.id,
        "model_ref": model_artifact_ref,
        "suite": suite,
        "suite_version": spec["version"],
        "num_samples": spec["num_samples"],
        "metrics": [m.model_dump(mode="json") for m in metrics],
        "passed": report.passed,
        "note": _STUB_NOTE,
    }


def get_evaluation_report(report_id: str) -> dict[str, Any]:
    """Retrieve a stored report. Read-only."""
    record = _stubstore.evaluations().get(report_id)
    if record is None:
        return {"success": False, "error": f"No report {report_id!r}."}
    return {"success": True, "report": record}


def compare_candidates(
    report_ids: list[str], primary_metric: str | None = None
) -> dict[str, Any]:
    """Rank candidate models by their reports. Pure code - no model judgement.

    Reports from different suites are refused rather than compared: ranking
    a perplexity score against a BLEU score would produce a confident,
    meaningless answer.
    """
    ids = [r for r in (report_ids or []) if r]
    if len(ids) < 2:
        return {"success": False, "error": "Pass at least two report_ids."}

    reports, missing = [], []
    for rid in ids:
        rec = _stubstore.evaluations().get(rid)
        (reports.append(EvaluationReport.model_validate(rec)) if rec
         else missing.append(rid))
    if missing:
        return {"success": False, "error": f"Unknown report ids: {missing}."}

    suites = {r.suite for r in reports}
    if len(suites) > 1:
        return {
            "success": False,
            "error": (
                f"Reports span different suites ({', '.join(sorted(suites))}); "
                f"their metrics are not comparable."
            ),
        }

    suite = reports[0].suite
    spec = SUITES[suite]
    metric = primary_metric or next(iter(spec["metrics"]))
    if metric not in spec["metrics"]:
        return {
            "success": False,
            "error": f"{metric!r} is not in suite {suite!r}. "
                     f"Available: {', '.join(spec['metrics'])}.",
        }
    higher_is_better = spec["metrics"][metric]["higher_is_better"]

    rows = []
    for r in reports:
        m = next((x for x in r.metrics if x.name == metric), None)
        if m is None:
            return {"success": False,
                    "error": f"Report {r.id} has no metric {metric!r}."}
        rows.append({
            "report_id": r.id,
            "model_ref": r.model_ref,
            metric: m.value,
            "passed_all_thresholds": r.passed,
        })

    rows.sort(key=lambda row: row[metric], reverse=higher_is_better)
    eligible = [r for r in rows if r["passed_all_thresholds"] is not False]

    return {
        "success": True,
        "suite": suite,
        "primary_metric": metric,
        "higher_is_better": higher_is_better,
        "ranking": rows,
        "winner": eligible[0] if eligible else None,
        "verdict": (
            f"{eligible[0]['model_ref']} leads on {metric} "
            f"({eligible[0][metric]}) and clears its thresholds."
            if eligible else
            "No candidate cleared every threshold; none should be released."
        ),
        "note": "Ranked by code against fixed thresholds. " + _STUB_NOTE,
    }


EVALUATION_TOOLS = [
    list_suites,
    run_evaluation,
    get_evaluation_report,
    compare_candidates,
]

__all__ = [
    "SUITES",
    "DEFAULT_THRESHOLDS",
    "list_suites",
    "run_evaluation",
    "get_evaluation_report",
    "compare_candidates",
    "EVALUATION_TOOLS",
]

