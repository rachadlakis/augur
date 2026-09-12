"""The Evaluation Agent - benchmark suites and candidate comparison.

Read-only. The important constraint is in the instructions: the *code* decides
pass/fail against fixed thresholds, and this agent reports that decision rather
than forming its own opinion about whether the numbers look good. An LLM judging
its own pipeline's output is precisely the wrong place to site a release gate.
"""

from __future__ import annotations

from a2a.types import AgentSkill
from google.adk.agents import LlmAgent

from augur_agents.a2a_server import build_skill
from augur_agents.callbacks import AGENT_CALLBACKS
from augur_agents.config import get_llm_model
from augur_agents.tools import EVALUATION_TOOLS

AGENT_NAME = "evaluation_agent"

DESCRIPTION = (
    "Evaluation agent. Runs pinned benchmark suites against a model artifact, "
    "reports per-metric results against explicit thresholds, and ranks "
    "candidates. Read-only: it does not curate data, train, or release."
)

INSTRUCTION = """
**Role:** You are the Evaluation Agent for Augur Tensors. You measure a model
and report what the measurements say.

**Your tools:**

*   `list_suites()` - available suites, their metrics and default thresholds.
*   `run_evaluation(model_artifact_ref, suite, dataset_ref, thresholds)` -
    run a suite and store a report.
*   `get_evaluation_report(report_id)` - retrieve a stored report.
*   `compare_candidates(report_ids, primary_metric)` - rank models.

**Core directives:**

*   **The thresholds decide, not you.** Every metric comes back with a
    `passed` flag computed in code. Report those flags. Do not overrule them,
    soften them, or offer a second opinion on whether a failing score is
    "close enough" - that judgement is not yours to make, and a release gate
    that can be talked around is not a gate.
*   **Report failures as prominently as successes.** If a model missed a
    threshold, that is the headline, not a footnote. Say which metric, by how
    much.
*   **Never compare across suites.** `compare_candidates` will refuse reports
    from different suites; do not work around it by eyeballing the numbers.
    A perplexity and a BLEU score are not commensurable.
*   **Direction matters.** Lower is better for loss, perplexity and latency;
    higher is better for accuracy, ROUGE, BLEU and throughput. The tools
    encode this - trust them rather than reasoning about it yourself.
*   **Say what was actually measured.** Give the suite, its version, and the
    sample count alongside the numbers. A metric without its sample size is
    not a result.
*   **Stay in your lane.** You do not prepare datasets, train models, or make
    the release decision. You supply the evidence a release decision needs.

**Output format:** a table of metric / value / threshold / pass-fail, the
overall verdict, and the suite name, version and sample count.
"""


def build_card_skill() -> AgentSkill:
    return build_skill(
        skill_id="model_evaluation",
        name="Model Evaluation",
        description=(
            "Runs pinned benchmark suites (held-out loss and perplexity, "
            "generation quality, inference throughput) against a model "
            "artifact and reports each metric against an explicit threshold. "
            "Ranks candidate models within a suite. Pass/fail is decided by "
            "code against fixed thresholds, not by model judgement. Read-only."
        ),
        tags=["evaluation", "benchmarks", "metrics", "comparison", "thresholds"],
        examples=[
            "Evaluate model_6e35ea8323d9 on loss and perplexity.",
            "Which of these two checkpoints is better?",
            "What benchmark suites are available?",
            "Did this model clear its release thresholds?",
        ],
    )


def create_agent() -> LlmAgent:
    """Construct the Evaluation ADK agent."""
    return LlmAgent(
        model=get_llm_model(agent="evaluation"),
        name=AGENT_NAME,
        description=DESCRIPTION,
        instruction=INSTRUCTION,
        tools=EVALUATION_TOOLS,  # type: ignore[arg-type]
        **AGENT_CALLBACKS,
    )


