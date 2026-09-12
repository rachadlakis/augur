"""Training plan, estimate, launch and monitoring for the Training Agent (stub).

Stands in for ``training-mcp`` plus a job manager.

**No GPU work happens here, and none ever should.** An agent server that hosted a
training loop would block its own event loop, die with the job, and put CUDA in
the same process as an LLM-driven tool dispatcher. The real implementation
launches an isolated ``torchrun`` subprocess or scheduler job; this stub keeps
the same contract - submit returns a job id immediately and state is read back
from a durable store.

Two properties are load-bearing and are *not* faked:

* ``submit_training_job`` **returns straight away**. It never waits for the run.
* The job store is SQLite, so a submitted job survives a worker restart and
  ``get_training_status`` still answers correctly afterwards. The polling path
  the orchestrator relies on for multi-hour runs is therefore real, even though
  the run itself is simulated by elapsed wall-clock time.

Planning maths is simplified stub implementations directly in this module.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from augur_agents import config
from augur_agents.contracts import (
    ModelArtifact,
    TrainingEstimate,
    TrainingJob,
    TrainingPlan,
    digest_of,
)
from augur_agents.tools import _stubstore, governance_tools


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _plan_from(plan: dict[str, Any]) -> TrainingPlan | None:
    try:
        return TrainingPlan.model_validate(plan)
    except Exception:
        return None


## =============================================================================
# Planning
## =============================================================================


def recommend_parallelism(
    param_count_b: float,
    gpu_count: int = 1,
    gpu_memory_gb: int = 80,
    hidden_size: int = 768,
    num_layers: int = 12,
    seq_len: int = 1024,
    global_batch_size: int = 64,
    micro_batch_size: int = 1,
    is_moe: bool = False,
) -> dict[str, Any]:
    """Suggest a sharding strategy, with a reason for every choice.

    Stub implementation: simplified heuristics based on model size and GPU count.
    """
    # Simple heuristic: small models use ZeRO-3, large models use TP+PP
    strategy = "fsdp" if gpu_count > 1 else "solo"
    zero_stage = 3 if gpu_count > 1 else 0
    tp = 1 if param_count_b < 10 else min(8, gpu_count // 2)
    pp = 1 if param_count_b < 100 else max(1, gpu_count // 8)
    
    rationale = f"For {param_count_b}B params on {gpu_count} GPUs: "
    if param_count_b < 10:
        rationale += "ZeRO-3 alone sufficient (< 10B)"
    elif param_count_b < 100:
        rationale += "ZeRO-3 + Tensor Parallelism (10B-100B)"
    else:
        rationale += "ZeRO-3 + TP + Pipeline Parallelism (> 100B)"
    
    # Basic memory estimation
    param_bytes = param_count_b * 1e9 * 2  # bf16
    grad_bytes = param_bytes
    optimizer_bytes = param_bytes * 2
    activation_bytes = seq_len * hidden_size * (global_batch_size // gpu_count) * num_layers * 2
    
    zero_factor = gpu_count if zero_stage == 3 else 1
    total_gb = (param_bytes + grad_bytes + optimizer_bytes) / zero_factor / 1e9 + activation_bytes / 1e9
    fits = total_gb <= gpu_memory_gb
    
    return {
        "success": True,
        "parallelism": {
            "strategy": strategy,
            "zero_stage": zero_stage,
            "dp": gpu_count if gpu_count <= 4 else max(1, gpu_count // 4),
            "tp": tp,
            "pp": pp,
            "cp": 1,
            "ep": 1,
            "gbs": global_batch_size,
            "recompute": "full" if param_count_b > 50 else "selective",
            "precision": "bf16",
        },
        "rationale": rationale,
        "memory": {
            "weights_grads_optim_gb": (param_bytes + grad_bytes + optimizer_bytes) / zero_factor / 1e9,
            "activations_gb": activation_bytes / 1e9,
            "total_gb": total_gb,
            "fits": fits,
            "headroom_gb": gpu_memory_gb - total_gb if fits else 0.0,
        },
        "warnings": [],
        "backend_gaps": [],
        "runnable_today": True,
        "note": "Heuristics distilled from the Ultra-Scale Playbook, not a profiled cost model. This configuration is runnable on the current backend.",
    }


def validate_training_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Check a ``TrainingPlan`` is internally consistent and executable."""
    tp = _plan_from(plan)
    if tp is None:
        return {
            "success": False,
            "error": "Not a valid TrainingPlan. Required: project_ref, "
                     "dataset_ref, base_model.",
        }

    findings: list[str] = []
    
    # Check for backend gaps: current backend only supports solo, ddp, fsdp with ZeRO-3
    gaps = []
    if tp.parallelism.tp > 1:
        gaps.append(f"Tensor Parallelism (tp={tp.parallelism.tp}) not yet supported")
    if tp.parallelism.pp > 1:
        gaps.append(f"Pipeline Parallelism (pp={tp.parallelism.pp}) not yet supported")
    if tp.parallelism.cp > 1:
        gaps.append(f"Context Parallelism (cp={tp.parallelism.cp}) not yet supported")
    if tp.parallelism.ep > 1:
        gaps.append(f"Expert Parallelism (ep={tp.parallelism.ep}) not yet supported")

    if tp.peft_type == "qlora" and not tp.peft_enabled:
        findings.append("peft_type=qlora but peft_enabled is false.")
    if tp.parallelism.strategy == "fsdp" and tp.peft_type == "qlora":
        findings.append(
            "QLoRA quantizes the base model, which does not compose with FSDP "
            "sharding in dist_kit - use solo or ddp for quantized runs."
        )
    if tp.epochs < 1:
        findings.append("epochs must be at least 1.")
    if not 0 < tp.learning_rate < 1:
        findings.append(f"learning_rate {tp.learning_rate} looks implausible.")

    return {
        "success": True,
        "valid": not findings and not gaps,
        "runnable_today": not gaps and not findings,
        "findings": findings or ["Plan is internally consistent."],
        "backend_gaps": gaps,
        "plan_digest": tp.digest(),
        "note": (
            f"Planned but not runnable on the current backend: {', '.join(gaps)}."
            if gaps else "Runnable on the current dist_kit backend."
        ),
    }


def estimate_training_job(plan: dict[str, Any]) -> dict[str, Any]:
    """Predict peak memory, wall-clock and cost for a plan.

    Stub implementation with simplified calculations.
    """
    tp = _plan_from(plan)
    if tp is None:
        return {"success": False, "error": "Not a valid TrainingPlan."}

    # Simple memory estimation
    param_bytes = tp.param_count_b * 1e9 * 2  # bf16
    grad_bytes = param_bytes
    optimizer_bytes = param_bytes * 2
    
    batch_per_gpu = tp.parallelism.gbs // max(1, tp.parallelism.dp)
    activation_bytes = tp.seq_len * tp.hidden_size * batch_per_gpu * tp.num_layers * 2
    
    zero_factor = tp.parallelism.dp if tp.parallelism.zero_stage == 3 else 1
    total_gb = (param_bytes + grad_bytes + optimizer_bytes) / zero_factor / 1e9 + activation_bytes / 1e9
    fits = total_gb <= tp.resources.gpu_memory_gb
    
    # Simple compute estimation: 6 FLOPs per token
    total_tokens = tp.parallelism.gbs * tp.seq_len * 100 * tp.epochs
    total_flops = 6 * tp.param_count_b * 1e9 * total_tokens
    
    # Assume 400 TFLOP/s sustained per GPU
    hours = total_flops / (400 * 1e12 * tp.resources.gpu_count * 3600)
    cost_usd = hours * tp.resources.gpu_count * 1.0  # $1/hour per GPU
    
    est = TrainingEstimate(
        peak_vram_gb_per_gpu=total_gb,
        fits=fits,
        total_flops=total_flops,
        estimated_hours=hours,
        estimated_cost_usd=cost_usd,
        assumptions=[
            f"Batch size per GPU: {batch_per_gpu}",
            f"~{total_tokens:,.0f} training tokens assumed",
            "400 TFLOP/s sustained per GPU (conservative estimate)",
        ],
    )
    return {
        "success": True,
        "estimate": est.model_dump(mode="json"),
        "memory_breakdown": {
            "weights_grads_optim_gb": (param_bytes + grad_bytes + optimizer_bytes) / zero_factor / 1e9,
            "activations_gb": activation_bytes / 1e9,
            "overhead_gb": 0.0,
            "headroom_gb": tp.resources.gpu_memory_gb - total_gb if fits else 0.0,
        },
        "plan_digest": tp.digest(),
        "note": (
            "Does not fit - the run would OOM. Reduce micro-batch, raise "
            "recomputation, or add GPUs."
            if not fits else
            "Deterministic heuristics, not a profiled measurement."
        ),
    }


## =============================================================================
# Job lifecycle
## =============================================================================


def _advance(record: dict[str, Any]) -> dict[str, Any]:
    """Move a stub job forward according to elapsed wall-clock time.

    Time-based rather than counter-based on purpose: it makes progress
    independent of how often anyone polls, and it stays correct across a process
    restart because only ``submitted_at`` is persisted.
    """
    job = TrainingJob.model_validate(record)
    if job.is_terminal:
        return record

    duration = max(1.0, config.STUB_TRAINING_DURATION_SECONDS)
    elapsed = (_now() - job.submitted_at).total_seconds()
    frac = min(1.0, elapsed / duration)

    # A short queue before the run starts, so TRAINING_QUEUED is observable.
    if frac < 0.1:
        job.state = "QUEUED"
        job.progress = 0.0
    elif frac < 1.0:
        job.state = "RUNNING"
        job.started_at = job.started_at or job.submitted_at
        job.progress = round(frac, 3)
    else:
        job.state = "COMPLETED"
        job.started_at = job.started_at or job.submitted_at
        job.finished_at = job.finished_at or _now()
        job.progress = 1.0

    job.heartbeat_at = _now()
    if job.progress > 0:
        # A plausible loss curve so the numbers are not obviously constant.
        job.metrics = {
            "train_loss": round(4.2 * math.exp(-2.2 * job.progress) + 1.55, 4),
            "learning_rate": round(5e-5 * (1 - 0.9 * job.progress), 8),
            "epoch": round(job.progress, 3),
        }

    if job.state == "COMPLETED" and not job.artifact_ref:
        artifact = ModelArtifact(
            job_ref=job.id,
            checkpoint_uri=f"s3://augur-dev/checkpoints/{job.id}/final/",
            format="safetensors",
            checksum=digest_of({"job": job.id, "digest": job.plan_digest})[:32],
            base_model=str(job.provenance.get("base_model", "unknown")),
            lineage={
                "plan_ref": job.plan_ref,
                "plan_digest": job.plan_digest,
                "dataset_ref": str(job.provenance.get("dataset_ref", "")),
            },
            provenance={"produced_by": "training_agent", "job": job.id},
        )
        _stubstore.artifacts()[artifact.id] = artifact.model_dump(mode="json")
        job.artifact_ref = artifact.id
        job.metrics["final_loss"] = job.metrics.get("train_loss", 0.0)
        governance_tools.record_audit(
            "training_completed", job=job.id, artifact=artifact.id
        )

    out = job.model_dump(mode="json")
    _stubstore.job_store().put(job.id, out)
    return out


def submit_training_job(
    plan: dict[str, Any], approval_token: str | None = None
) -> dict[str, Any]:
    """Launch a training run. **Paid and mutating - requires approval.**

    Returns as soon as the job is registered. It does *not* wait for the run:
    poll ``get_training_status`` afterwards, on a later turn if necessary.
    """
    tp = _plan_from(plan)
    if tp is None:
        return {"success": False, "error": "Not a valid TrainingPlan."}

    digest = tp.digest()
    # The approval is bound to the plan digest, so an approval obtained for a
    # different model, dataset, GPU count or sharding layout will not match.
    decision = governance_tools.check_policy(
        "submit_training_job", {"plan_digest": digest}, approval_token
    )
    if not decision["allowed"]:
        return {
            "success": False,
            "error": decision["reason"],
            "needs_approval": True,
            "action": "submit_training_job",
            "params": {"plan_digest": digest},
            "plan_digest": digest,
        }

    # Simple backend gap checking: current backend only supports solo, ddp, fsdp with ZeRO-3
    gaps = []
    if tp.parallelism.tp > 1:
        gaps.append(f"Tensor Parallelism (tp={tp.parallelism.tp}) not yet supported")
    if tp.parallelism.pp > 1:
        gaps.append(f"Pipeline Parallelism (pp={tp.parallelism.pp}) not yet supported")
    if tp.parallelism.cp > 1:
        gaps.append(f"Context Parallelism (cp={tp.parallelism.cp}) not yet supported")
    if tp.parallelism.ep > 1:
        gaps.append(f"Expert Parallelism (ep={tp.parallelism.ep}) not yet supported")
    
    if gaps:
        return {
            "success": False,
            "error": (
                f"The current dist_kit backend cannot execute this plan: "
                f"{', '.join(gaps)}. It supports solo, ddp and fsdp (ZeRO-3) on "
                f"a single node. Re-plan within those, or wait for the backend."
            ),
            "backend_gaps": gaps,
            "plan_digest": digest,
        }

    job = TrainingJob(
        plan_ref=tp.id,
        plan_digest=digest,
        state="QUEUED",
        provenance={
            "base_model": tp.base_model,
            "dataset_ref": tp.dataset_ref,
            "strategy": tp.parallelism.strategy,
            "gpu_count": tp.resources.gpu_count,
        },
    )
    _stubstore.job_store().put(job.id, job.model_dump(mode="json"))
    governance_tools.record_audit(
        "training_submitted", job=job.id, plan_digest=digest,
        gpu_count=tp.resources.gpu_count,
    )
    return {
        "success": True,
        "job_id": job.id,
        "state": "QUEUED",
        "plan_digest": digest,
        "submitted_at": job.submitted_at.isoformat(),
        "note": (
            "Submitted. This call does not wait for the run - poll "
            "get_training_status with this job_id. A real run takes hours, so "
            "it is correct to report the job id to the user and check back "
            "later rather than blocking."
        ),
    }


def get_training_status(job_id: str) -> dict[str, Any]:
    """Current state of a job. Read-only; safe to call repeatedly."""
    record = _stubstore.job_store().get(job_id)
    if record is None:
        return {"success": False, "error": f"No job {job_id!r}."}
    job = _advance(record)
    remaining = None
    if job["state"] in {"QUEUED", "RUNNING"}:
        remaining = round(
            max(0.0, config.STUB_TRAINING_DURATION_SECONDS * (1 - job["progress"])), 1
        )
    return {
        "success": True,
        "job_id": job["id"],
        "state": job["state"],
        "progress": job["progress"],
        "metrics": job["metrics"],
        "artifact_ref": job["artifact_ref"],
        "failure_reason": job["failure_reason"],
        "is_terminal": job["state"] in {"COMPLETED", "FAILED", "CANCELED"},
        "seconds_remaining": remaining,
    }


def stream_training_logs(job_id: str, tail: int = 10) -> dict[str, Any]:
    """Recent log lines for a job. Read-only."""
    record = _stubstore.job_store().get(job_id)
    if record is None:
        return {"success": False, "error": f"No job {job_id!r}."}
    job = _advance(record)
    steps = max(1, int(job["progress"] * 100))
    lines = [
        f"step {s:>4}/100  loss {4.2 * math.exp(-2.2 * s / 100) + 1.55:.4f}  "
        f"lr {5e-5 * (1 - 0.9 * s / 100):.2e}"
        for s in range(max(1, steps - tail + 1), steps + 1)
    ]
    if job["state"] == "COMPLETED":
        lines.append(f"training complete - artifact {job['artifact_ref']}")
    return {"success": True, "job_id": job_id, "state": job["state"], "lines": lines}


def cancel_training_job(
    job_id: str, approval_token: str | None = None
) -> dict[str, Any]:
    """Stop a running job. **Destructive - requires approval unless queued.**

    A queued job has not consumed GPU time, so cancelling it destroys nothing
    and needs no approval. A running job has partial results worth protecting.
    """
    record = _stubstore.job_store().get(job_id)
    if record is None:
        return {"success": False, "error": f"No job {job_id!r}."}
    job_dict = _advance(record)
    job = TrainingJob.model_validate(job_dict)

    if job.is_terminal:
        return {
            "success": False,
            "error": f"Job {job_id} is already {job.state}; nothing to cancel.",
        }

    if job.state != "QUEUED":
        decision = governance_tools.check_policy(
            "cancel_training_job", {"job_id": job_id}, approval_token
        )
        if not decision["allowed"]:
            return {
                "success": False,
                "error": decision["reason"],
                "needs_approval": True,
                "action": "cancel_training_job",
                "params": {"job_id": job_id},
            }

    job.state = "CANCELED"
    job.finished_at = _now()
    job.failure_reason = "canceled by request"
    _stubstore.job_store().put(job.id, job.model_dump(mode="json"))
    governance_tools.record_audit("training_canceled", job=job.id)
    return {"success": True, "job_id": job_id, "state": "CANCELED"}


def resume_training_job(
    job_id: str, checkpoint_ref: str | None = None, approval_token: str | None = None
) -> dict[str, Any]:
    """Restart a stopped job as a new attempt. **Paid - requires approval.**"""
    record = _stubstore.job_store().get(job_id)
    if record is None:
        return {"success": False, "error": f"No job {job_id!r}."}
    job = TrainingJob.model_validate(record)

    if job.state not in {"FAILED", "CANCELED"}:
        return {
            "success": False,
            "error": f"Job {job_id} is {job.state}; only FAILED or CANCELED jobs "
                     f"can be resumed.",
        }

    decision = governance_tools.check_policy(
        "resume_training_job", {"job_id": job_id, "checkpoint_ref": checkpoint_ref},
        approval_token,
    )
    if not decision["allowed"]:
        return {
            "success": False,
            "error": decision["reason"],
            "needs_approval": True,
            "action": "resume_training_job",
            "params": {"job_id": job_id, "checkpoint_ref": checkpoint_ref},
        }

    job.attempt += 1
    job.state = "QUEUED"
    job.submitted_at = _now()
    job.started_at = None
    job.finished_at = None
    job.failure_reason = None
    job.progress = 0.0
    _stubstore.job_store().put(job.id, job.model_dump(mode="json"))
    governance_tools.record_audit(
        "training_resumed", job=job.id, attempt=job.attempt
    )
    return {
        "success": True, "job_id": job.id, "state": "QUEUED",
        "attempt": job.attempt,
        "note": "Resumed as a new attempt; poll get_training_status.",
    }


def get_model_artifact(artifact_ref: str) -> dict[str, Any]:
    """The checkpoint a completed job produced. Read-only."""
    record = _stubstore.artifacts().get(artifact_ref)
    if record is None:
        return {"success": False, "error": f"No artifact {artifact_ref!r}."}
    return {"success": True, "artifact": record}


TRAINING_TOOLS = [
    recommend_parallelism,
    validate_training_plan,
    estimate_training_job,
    submit_training_job,
    get_training_status,
    stream_training_logs,
    cancel_training_job,
    resume_training_job,
    get_model_artifact,
]

__all__ = [
    "recommend_parallelism",
    "validate_training_plan",
    "estimate_training_job",
    "submit_training_job",
    "get_training_status",
    "stream_training_logs",
    "cancel_training_job",
    "resume_training_job",
    "get_model_artifact",
    "TRAINING_TOOLS",
]

