"""Versioned contracts exchanged between agents.

Agents never hand each other worker-local filesystem paths. They exchange these
Pydantic models, which carry stable identifiers, a ``schema_version``, and
provenance, so a result stays meaningful after the process that produced it is
gone.

This is the lightweight precursor to the full ``augur_contracts`` package in
IMPLEMENTATION_PLAN Phase 1: the shapes and the digest semantics are real, but
JSON Schemas are not generated or compatibility-tested yet.

The one piece of behaviour worth understanding is :meth:`TrainingPlan.digest`.
An approval is bound to that digest, so changing the model, the dataset, the GPU
count, or the parallelism plan produces a different digest and silently
invalidates the approval rather than letting it authorize a different run.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION: Literal["0.1.0"] = "0.1.0"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def canonical_json(payload: Any) -> str:
    """Stable JSON for hashing: sorted keys, no incidental whitespace.

    Used for action digests. Two structurally equal payloads must produce the
    same string on any machine, or an approval would not survive a round trip.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def digest_of(payload: Any) -> str:
    """``sha256`` over :func:`canonical_json` - the identity of an action."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


class Contract(BaseModel):
    """Shared envelope: every persisted contract is versioned and traceable."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1.0"] = SCHEMA_VERSION
    created_at: datetime = Field(default_factory=_now)
    # Free-form lineage: who produced this, from what inputs, with what tool.
    provenance: dict[str, Any] = Field(default_factory=dict)


class DataQualityReport(Contract):
    """Normalized quality metadata for a provider or market snapshot."""

    source: str
    timestamp: str | datetime
    latency_ms: int = 0
    freshness: float = 0.0
    quality_score: float = 0.0
    missing_fields: list[str] = Field(default_factory=list)
    anomalies: list[str] = Field(default_factory=list)

    @field_validator("freshness", "quality_score")
    @classmethod
    def _bounded_float(cls, value: float, info: Any) -> float:
        numeric = float(value)
        if not 0.0 <= numeric <= 1.0:
            raise ValueError(f"{info.field_name} must be between 0.0 and 1.0")
        return numeric


class MarketSnapshot(Contract):
    """Normalized market state used by specialist agents."""

    asset: str
    timestamp: datetime
    price: float
    ohlcv: dict[str, dict[str, float]] = Field(default_factory=dict)
    volume: float = 0.0
    spread: float = 0.0
    liquidity: float = 0.0
    volatility: dict[str, float] = Field(default_factory=dict)
    derivatives: dict[str, Any] = Field(default_factory=dict)

    def is_fresh(self, *, max_age_seconds: int = 10) -> bool:
        age_seconds = (datetime.now(timezone.utc) - self.timestamp).total_seconds()
        return age_seconds <= max_age_seconds

    def data_quality(self) -> DataQualityReport:
        age_seconds = (datetime.now(timezone.utc) - self.timestamp).total_seconds()
        freshness = max(0.0, min(1.0, 1.0 - (age_seconds / 60.0)))
        quality_score = max(0.0, min(1.0, freshness * 0.7 + self.liquidity * 0.3))

        missing_fields: list[str] = []
        if not self.ohlcv:
            missing_fields.append("ohlcv")
        if self.volume <= 0:
            missing_fields.append("volume")
        if self.spread <= 0:
            missing_fields.append("spread")
        if self.liquidity <= 0:
            missing_fields.append("liquidity")

        anomalies: list[str] = []
        if not self.is_fresh(max_age_seconds=10):
            anomalies.append("stale_market_data")
        if self.spread > 0.01:
            anomalies.append("wide_spread")

        return DataQualityReport(
            source="market_snapshot",
            timestamp=self.timestamp,
            latency_ms=max(0, int(age_seconds * 1000)),
            freshness=freshness,
            quality_score=quality_score,
            missing_fields=missing_fields,
            anomalies=anomalies,
        )


class TradeDecision(Contract):
    """Structured output for the orchestrator and risk gate."""

    decision: Literal["BUY", "SELL", "HOLD", "NO_TRADE"]
    confidence: float = 0.0
    evidence_quality: float = 0.0
    data_quality: float = 0.0
    reason: str = ""
    thesis: str | None = None
    required_conditions: list[str] = Field(default_factory=list)

    @field_validator("confidence", "evidence_quality", "data_quality")
    @classmethod
    def _validate_probability(cls, value: float, info: Any) -> float:
        numeric = float(value)
        if not 0.0 <= numeric <= 1.0:
            raise ValueError(f"{info.field_name} must be between 0.0 and 1.0")
        return numeric


## =============================================================================
# Project
## =============================================================================


class ProjectSpec(Contract):
    """What the user actually asked for. The root of every workflow."""

    id: str = Field(default_factory=lambda: _new_id("proj"))
    objective: str
    base_model: str
    task_type: Literal["llm", "seq2seq", "encoder"] = "llm"
    # Free-form limits the plan must respect, e.g. {"max_cost_usd": 50}.
    constraints: dict[str, Any] = Field(default_factory=dict)
    budget_usd: float | None = None
    owner: str | None = None


## =============================================================================
# Data
## =============================================================================


class DatasetSplit(Contract):
    name: str
    num_rows: int
    num_tokens: int | None = None


class DatasetManifest(Contract):
    """An immutable description of exactly which data a run may use.

    ``storage_uri`` is a durable artifact URI, never a worker-local path, and
    ``checksum`` is what makes a later run reproducible.
    """

    id: str = Field(default_factory=lambda: _new_id("ds"))
    source: str                       # e.g. "wikitext"
    revision: str                     # dataset revision / config, pinned
    license: str
    splits: list[DatasetSplit] = Field(default_factory=list)
    checksum: str
    storage_uri: str
    transforms: list[str] = Field(default_factory=list)
    text_column: str = "text"


class DatasetQualityReport(Contract):
    id: str = Field(default_factory=lambda: _new_id("dsq"))
    dataset_ref: str
    passed: bool
    findings: list[str] = Field(default_factory=list)


## =============================================================================
# Training
## =============================================================================


class ParallelismConfig(BaseModel):
    """How the run is sharded across GPUs.

    The names follow the Ultra-Scale Playbook's five axes (see
    ``docs/ultrascale_playbook.md``): data, tensor, pipeline, context, expert.
    ``strategy`` is the narrower thing the current dist_kit backend can actually
    execute; a plan may legitimately describe tp/pp/cp/ep > 1 while the backend
    still reports it as un-runnable, so the intent survives until the executor
    catches up.
    """

    model_config = ConfigDict(extra="forbid")

    strategy: Literal["solo", "ddp", "fsdp"] = "fsdp"
    zero_stage: Literal[0, 1, 2, 3] = 3      # 3 == FSDP == fully sharded
    dp: int = 1                              # data parallelism degree
    tp: int = 1                              # tensor parallelism (keep <= 8, intra-node)
    pp: int = 1                              # pipeline parallelism
    cp: int = 1                              # context parallel (long sequences)
    ep: int = 1                              # expert parallelism (MoE only)
    mbs: int = 1                             # micro-batch size
    gbs: int = 1                             # global batch size
    grad_accum: int = 1
    recompute: Literal["none", "selective", "full"] = "selective"
    precision: Literal["fp32", "bf16", "fp16", "fp8"] = "bf16"

    @property
    def world_size(self) -> int:
        """GPUs implied by the sharding plan."""
        return self.dp * self.tp * self.pp * self.cp


class ResourceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gpu_count: int = 1
    gpu_type: str = "A100-80GB"
    gpu_memory_gb: int = 80
    nodes: int = 1


class TrainingEstimate(Contract):
    """What a run is predicted to cost, before anyone approves it."""

    peak_vram_gb_per_gpu: float ## Peak VRAM usage per GPU in GB
    fits: bool                  ## Whether the model fits in the available GPU memory
    total_flops: float          ## Total floating point operations required for the run
    estimated_hours: float      ## Estimated number of hours the run will take
    estimated_cost_usd: float   ## Estimated cost of the run in USD
    assumptions: list[str] = Field(default_factory=list) ## Assumptions made for the training estimate


class TrainingPlan(Contract):
    """The exact, immutable description of a run. Approvals bind to its digest."""

    id: str = Field(default_factory=lambda: _new_id("plan"))
    project_ref: str        ## Reference to the project this training plan belongs to
    dataset_ref: str        ## Reference to the dataset used for this training plan
    base_model: str         ## Base model used for this training plan
    # Model shape, needed by the memory/parallelism math.
    hidden_size: int = 768          ## Hidden size of the model
    num_layers: int = 12            ## Number of layers in the model
    num_heads: int = 12             ## Number of attention heads in the model
    seq_len: int = 1024             ## Sequence length for the model inputs
    param_count_b: float = 0.1      ## Parameter count in billions
    is_moe: bool = False           ## Whether the model is a mixture of experts (MoE)

    epochs: int = 1                  ## Number of training epochs
    learning_rate: float = 5e-5      ## Learning rate for the optimizer
    parallelism: ParallelismConfig = Field(default_factory=ParallelismConfig)  ## Parallelism configuration for the training run
    resources: ResourceRequest = Field(default_factory=ResourceRequest)        ## Resource requirements for the training run

    peft_enabled: bool = False
    peft_type: Literal["none", "lora", "qlora"] = "none"

    # Which code produced/executes this plan; part of reproducibility.
    code_revision: str = "dist_kit@local"
    estimate: TrainingEstimate | None = None

    def digest(self) -> str:
        """Canonical identity of this plan.

        Deliberately excludes ``created_at``, ``provenance``, ``id`` and the
        ``estimate`` - two plans that would run identically must digest
        identically, and an estimate is a prediction *about* the plan, not part
        of it. Everything that changes what actually runs is included, so an
        approval cannot be carried over to a different model, dataset, GPU count
        or sharding layout.
        """
        payload = self.model_dump(
            mode="json",
            exclude={"id", "created_at", "provenance", "estimate", "schema_version"},
        )
        return digest_of(payload)


class TrainingJob(Contract):
    """Durable state of one launched run. Owned by the job manager, not the LLM."""

    id: str = Field(default_factory=lambda: _new_id("tj"))
    plan_ref: str
    plan_digest: str
    state: Literal[
        "QUEUED", "RUNNING", "COMPLETED", "FAILED", "CANCELED"
    ] = "QUEUED"
    attempt: int = 1
    submitted_at: datetime = Field(default_factory=_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    heartbeat_at: datetime | None = None
    progress: float = 0.0                    # 0.0 - 1.0
    metrics: dict[str, float] = Field(default_factory=dict)
    artifact_ref: str | None = None
    failure_reason: str | None = None

    @property
    def is_terminal(self) -> bool:
        return self.state in {"COMPLETED", "FAILED", "CANCELED"}


class ModelArtifact(Contract):
    """A produced checkpoint, addressed by URI and verified by checksum."""

    id: str = Field(default_factory=lambda: _new_id("model"))
    job_ref: str
    checkpoint_uri: str
    format: Literal["safetensors", "dcp", "pt"] = "safetensors"
    checksum: str
    base_model: str
    adapters: list[str] = Field(default_factory=list)
    tokenizer_uri: str | None = None
    # Everything needed to explain where this came from.
    lineage: dict[str, str] = Field(default_factory=dict)


## =============================================================================
# Evaluation
## =============================================================================


class MetricResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    value: float
    threshold: float | None = None
    passed: bool | None = None


class EvaluationReport(Contract):
    """Benchmark results. Thresholds decide pass/fail - not model prose."""

    id: str = Field(default_factory=lambda: _new_id("eval"))
    model_ref: str
    suite: str
    suite_version: str = "0.1.0"
    dataset_ref: str | None = None
    metrics: list[MetricResult] = Field(default_factory=list)
    num_samples: int = 0
    errors: list[str] = Field(default_factory=list)

    @property
    def passed(self) -> bool | None:
        """True only if every metric that HAS a threshold passed it."""
        judged = [m.passed for m in self.metrics if m.passed is not None]
        return all(judged) if judged else None


## =============================================================================
# Governance
## =============================================================================


class ApprovalRequest(Contract):
    """A request for a human to authorize one exact action.

    ``action_digest`` is the whole point: the approval authorizes *this* action,
    with these parameters. A free-form "yes go ahead" in chat is not an
    authorization token, and an approval for a 1-GPU run cannot be spent on a
    64-GPU one.
    """

    id: str = Field(default_factory=lambda: _new_id("appr"))
    action: str                              # e.g. "submit_training_job"
    action_digest: str
    risk: Literal["read_only", "paid", "destructive", "public"] = "paid"
    summary: str = ""
    estimate: dict[str, Any] = Field(default_factory=dict)
    expires_at: datetime | None = None
    requested_scopes: list[str] = Field(default_factory=list)

    granted: bool = False
    granted_by: str | None = None
    granted_at: datetime | None = None
    consumed: bool = False

    def is_spendable(self, *, at: datetime | None = None) -> bool:
        """Granted, not already spent, not expired."""
        if not self.granted or self.consumed:
            return False
        if self.expires_at is None:
            return True
        return (at or _now()) < self.expires_at


__all__ = [
    "SCHEMA_VERSION",
    "canonical_json",
    "digest_of",
    "Contract",
    "DataQualityReport",
    "MarketSnapshot",
    "TradeDecision",
    "ProjectSpec",
    "DatasetSplit",
    "DatasetManifest",
    "DatasetQualityReport",
    "ParallelismConfig",
    "ResourceRequest",
    "TrainingEstimate",
    "TrainingPlan",
    "TrainingJob",
    "ModelArtifact",
    "MetricResult",
    "EvaluationReport",
    "ApprovalRequest",
]
