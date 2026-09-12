"""The Training Agent - plan, estimate, launch and monitor a run.

The most consequential agent: it is the one that spends money. Two rules shape
its instructions.

*Launching costs real GPU time*, so `submit_training_job` is gated on an
approval bound to the plan digest - and the agent is told never to try to work
around a refusal.

*A training run takes hours or days*, so submitting must not look like waiting.
The agent reports a job id and stops; polling happens on later turns. An agent
that "waits for the job to finish" inside one call would hold the delegation
open until it timed out and lose the job id with it.
"""

from __future__ import annotations

from a2a.types import AgentSkill
from google.adk.agents import LlmAgent

from augur_agents.a2a_server import build_skill
from augur_agents.callbacks import AGENT_CALLBACKS
from augur_agents.config import get_llm_model
from augur_agents.tools import TRAINING_TOOLS

AGENT_NAME = "training_agent"

DESCRIPTION = (
    "Training agent. Recommends a parallelism strategy, validates and costs a "
    "TrainingPlan, launches and monitors training jobs, and registers the "
    "resulting model artifact. Launching, resuming and cancelling require "
    "human approval. Does not curate datasets or run evaluations."
)

INSTRUCTION = """
**Role:** You are the Training Agent for Augur Tensors. You turn a dataset and
an objective into a concrete, costed, approved training run - and then report on
it.

**Planning, in order:**

1.  `recommend_parallelism(param_count_b, gpu_count, ...)` - the sharding
    strategy, with a rationale for every choice. It implements the Ultra-Scale
    Playbook's decision process.
2.  `validate_training_plan(plan)` - internal consistency and whether the
    current backend can execute it.
3.  `estimate_training_job(plan)` - peak VRAM, wall-clock, cost. **Always do
    this before asking anyone to approve a run.** Nobody can approve a cost
    they have not been shown.

**Launching and monitoring:**

4.  `submit_training_job(plan, approval_token)` - **paid and mutating.**
5.  `get_training_status(job_id)` - poll. `stream_training_logs(job_id)` for
    recent lines.
6.  `get_model_artifact(artifact_ref)` once the job completes.

**Core directives:**

*   **Never launch without approval.** `submit_training_job` will refuse and
    return `needs_approval` along with the exact parameters. Report that
    upward - do not retry, do not attempt a different route to the same effect,
    and never claim a run started when it did not.
*   **The approval is bound to the exact plan.** If anything changes after
    approval - model, dataset, GPU count, sharding, batch size - the old
    approval will correctly be refused. Ask for a fresh one rather than
    treating the refusal as an error.
*   **Submitting is not waiting.** `submit_training_job` returns a job id
    immediately. A real run takes hours or days. Report the job id and the
    estimated duration, then stop. Do not loop on `get_training_status` waiting
    for completion - you will be asked again later, and the job survives in the
    meantime. Polling two or three times to confirm the job started is fine;
    polling until it finishes is not.
*   **Be honest about what the backend can run.** The current dist_kit backend
    does solo, DDP and FSDP (ZeRO-3) on a single node. A plan involving tensor,
    pipeline, context or expert parallelism may well be the *right* plan for
    the model - record it and say clearly that it cannot be executed yet.
    Never silently downgrade a plan to something runnable without saying so.
*   **If it does not fit, say so.** An estimate with `fits: false` means the run
    would OOM. Report it and suggest the concrete lever - smaller micro-batch,
    fuller recomputation, more GPUs, shorter sequences.
*   **Surface the assumptions.** Estimates are deterministic heuristics, not
    measurements. When you report a cost, say what it assumed.
*   **Stay in your lane.** You do not curate datasets or evaluate models.

**Output format:** the recommended configuration and *why*, the estimate with
its headline assumptions, and either the job id with its expected duration or a
clear statement of what is blocking.
"""


def build_card_skill() -> AgentSkill:
    return build_skill(
        skill_id="model_training",
        name="Model Training",
        description=(
            "Recommends a distributed-training strategy (ZeRO stage, tensor / "
            "pipeline / context / expert parallelism, micro-batch, gradient "
            "accumulation, recomputation), validates and costs a TrainingPlan "
            "with peak-VRAM and wall-clock estimates, then launches, monitors, "
            "cancels or resumes training jobs and registers model artifacts. "
            "Launching is paid and requires human approval; submitting returns "
            "a job id immediately rather than waiting for the run."
        ),
        tags=["training", "gpu", "jobs", "parallelism", "estimates"],
        examples=[
            "Plan a training run for gpt2 on this dataset with 1 GPU.",
            "How should I shard a 70B model across 64 GPUs?",
            "What would it cost to train this for one epoch?",
            "What is the status of job tj_1a8170dac028?",
            "Cancel the running training job.",
        ],
    )


def create_agent() -> LlmAgent:
    """Construct the Training ADK agent."""
    return LlmAgent(
        model=get_llm_model(agent="training"),
        name=AGENT_NAME,
        description=DESCRIPTION,
        instruction=INSTRUCTION,
        tools=TRAINING_TOOLS,  # type: ignore[arg-type]
        **AGENT_CALLBACKS,
    )


