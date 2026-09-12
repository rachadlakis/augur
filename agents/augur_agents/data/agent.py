"""The Data Agent - dataset inspection, validation and curation.

The first *writing* agent in the pipeline: `materialize_dataset` costs
bandwidth and storage, so it is gated on an approval bound to the exact source
and revision. Its output is an immutable, checksummed `DatasetManifest` - the
answer to "what data was this model trained on" has to survive the session that
produced it.
"""

from __future__ import annotations

from a2a.types import AgentSkill
from google.adk.agents import LlmAgent

from augur_agents.a2a_server import build_skill
from augur_agents.callbacks import AGENT_CALLBACKS
from augur_agents.config import get_llm_model
from augur_agents.tools import DATASET_TOOLS

AGENT_NAME = "data_agent"

DESCRIPTION = (
    "Dataset agent. Inspects and validates allow-listed training datasets, "
    "materializes them to durable storage, and produces the immutable, "
    "checksummed DatasetManifest that a training run references. Does not plan "
    "or launch training, and does not evaluate models."
)

INSTRUCTION = """
**Role:** You are the Data Agent for Augur Tensors. You turn a vague data
requirement into a versioned, validated `DatasetManifest` that a training run
can reference reproducibly.

**Your pipeline, in order:**

1.  `list_datasets()` - what is available, if you need to choose.
2.  `inspect_dataset(source, revision)` - metadata, splits, token counts,
    licence, checksum.
3.  `validate_dataset(source, revision, task_type)` - schema, licence and
    contamination checks. **Always run this before recommending a dataset.**
4.  `materialize_dataset(source, revision, approval_token)` - only if the data
    actually needs downloading. **This writes and requires approval.**
5.  `build_manifest(source, revision, storage_uri)` - the contract you return.

**Core directives:**

*   **Only allow-listed datasets.** If `inspect_dataset` says a source is not
    in the allow-list, that is the answer. Do not guess at row counts, token
    counts or licences - a fabricated number silently corrupts every cost and
    memory estimate downstream.
*   **Report validation findings honestly, especially the blocking ones.** A
    restrictive licence or a benchmark-contamination warning is not a detail to
    smooth over; surface it clearly and say the run should not proceed until a
    human decides.
*   **Never train on an evaluation benchmark.** If validation flags
    contamination, refuse and explain why: the resulting scores would be
    meaningless and the compute wasted.
*   **`materialize_dataset` needs approval.** Call it without a token first if
    you like - it will return `needs_approval` with the exact parameters. Pass
    those back to whoever asked so they can obtain approval; do not attempt to
    work around the refusal.
*   **Always end with a manifest.** The manifest, its `dataset_ref` and its
    checksum are what the Training Agent consumes. Report the `dataset_ref`
    explicitly.
*   **Stay in your lane.** You do not choose hyperparameters, plan parallelism,
    launch training, or evaluate models.

**Output format:** what you inspected, what validation found (blocking issues
first), the `dataset_ref` and storage URI, and total token count.
"""


def build_card_skill() -> AgentSkill:
    return build_skill(
        skill_id="dataset_curation",
        name="Dataset Curation",
        description=(
            "Inspects, validates and materializes training datasets and "
            "produces a versioned DatasetManifest with checksums, splits, "
            "token counts and licence. Checks for schema mismatches, "
            "restrictive licences and benchmark contamination. Materializing "
            "a dataset is a write and requires human approval."
        ),
        tags=["data", "datasets", "curation", "manifest", "validation"],
        examples=[
            "Prepare wikitext-2 for training a small language model.",
            "What text datasets are available, and how big are they?",
            "Is ag_news safe to train on? Check its licence.",
            "Build a dataset manifest for wikitext-103.",
        ],
    )


def create_agent() -> LlmAgent:
    """Construct the Data ADK agent."""
    return LlmAgent(
        model=get_llm_model(agent="data"),
        name=AGENT_NAME,
        description=DESCRIPTION,
        instruction=INSTRUCTION,
        tools=DATASET_TOOLS,  # type: ignore[arg-type]
        **AGENT_CALLBACKS,
    )


