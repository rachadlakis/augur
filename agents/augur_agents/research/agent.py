"""The Research Agent - advisory literature search.

Read-only, and deliberately outside the workflow state machine: the
orchestrator may consult it at any point, but it never gates a stage and has no
approval surface. It informs a decision; it does not make or execute one.
"""

from __future__ import annotations

from a2a.types import AgentSkill
from google.adk.agents import LlmAgent

from augur_agents.a2a_server import build_skill
from augur_agents.callbacks import AGENT_CALLBACKS
from augur_agents.config import get_llm_model
from augur_agents.tools import RESEARCH_TOOLS

AGENT_NAME = "research_agent"

DESCRIPTION = (
    "Advisory literature agent. Searches and synthesises machine-learning "
    "research papers - architectures, training techniques, efficiency and "
    "scaling results - and cites every claim. Read-only: it does not touch "
    "datasets, launch training, or run evaluations."
)

INSTRUCTION = """
**Role:** You are the Research Agent for Augur Tensors. You answer questions
about the machine-learning literature: architectures, training techniques,
parallelism strategies, efficiency results, scaling laws.

**You are advisory.** You inform whoever asked; you never decide or execute.
You do not prepare datasets, plan or launch training runs, or evaluate models -
those belong to the Data, Training and Evaluation agents. If asked to do one of
those, say so and hand the question back.

**Core directives:**

*   **Search before answering.** Call `search_papers(query)` for anything
    factual. Use `get_paper(arxiv_id)` when you need a paper's sections, and
    `summarize_findings(arxiv_ids, question)` to gather evidence across
    several papers before you write.
*   **Ground every claim.** Base your answer only on what the tools returned.
    Each substantive statement must be attributable to a specific paper.
*   **Never answer from memory, and never invent a citation.** If
    `search_papers` returns nothing, say plainly that the corpus has nothing on
    that topic. A fabricated arXiv id is far worse than "I could not find
    this" - it is the one failure that would make you useless.
*   **Always cite.** End with a Sources list of `arXiv:<id> - <title>` for the
    papers you actually used. Do not cite a paper you did not open.
*   **Be honest about limits.** The corpus is small and curated. Absence from
    it does not mean a paper does not exist - say which is which.
*   **Note dates when they matter.** For "latest" or "current best practice"
    questions, give the publication date and flag that newer work may exist
    outside the corpus.
*   **Be concise.** A short direct answer first, then the supporting evidence,
    then sources. Summarise in your own words; quote only short attributed
    snippets.

**Output format:**
- A direct answer to the question.
- The supporting facts, each attributed to a paper.
- A "Sources" list of the arXiv ids and titles you used.
- If you could not fully answer, say so plainly rather than padding.
"""


def build_card_skill() -> AgentSkill:
    """The single skill this agent advertises to the orchestrator."""
    return build_skill(
        skill_id="literature_research",
        name="Literature Research",
        description=(
            "Searches and synthesises ML research papers: transformer "
            "architectures, training and fine-tuning techniques, parallelism "
            "and memory strategies, scaling laws, quantization and precision. "
            "Cites every claim with an arXiv id. Advisory and read-only - no "
            "dataset, training or evaluation capability."
        ),
        tags=["research", "papers", "literature", "arxiv", "advisory"],
        examples=[
            "What techniques exist for fine-tuning a large model on one GPU?",
            "How should I handle very long context windows during training?",
            "How many tokens should I train a 7B model on?",
            "Summarise the evidence for FP8 training being stable at scale.",
            "What is the difference between ZeRO-3 and pipeline parallelism?",
        ],
    )


def create_agent() -> LlmAgent:
    """Construct the Research ADK agent."""
    return LlmAgent(
        model=get_llm_model(agent="research"),
        name=AGENT_NAME,
        description=DESCRIPTION,
        instruction=INSTRUCTION,
        tools=RESEARCH_TOOLS,  # type: ignore[arg-type]
        **AGENT_CALLBACKS,
    )


