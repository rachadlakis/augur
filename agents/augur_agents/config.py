"""Configuration for the Augur agent layer.

Everything is read from the environment (repo-root ``.env``; see
``.env.example``). Nothing here does network I/O or constructs a model, so
importing this module is always cheap and side-effect free.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

# One .env for the whole workspace. `find_dotenv` walks up from the caller, so
# this resolves the repo root whether an agent is started from the root, from
# agents/, or from inside the package.
_DOTENV = find_dotenv(usecwd=True) or str(Path(__file__).resolve().parents[2] / ".env")
load_dotenv(_DOTENV)

REPO_ROOT = Path(_DOTENV).resolve().parent if _DOTENV else Path.cwd()

# User / tenant context - fixed for now, change when multi-tenant.
USER_ID = os.getenv("USER_ID", "demo_user_001")
TENANT_ID = os.getenv("TENANT_ID", "demo_tenant_001")


## =============================================================================
# LLM provider and per-agent model selection
#
# Every agent talks to its model through LiteLLM (google.adk ... LiteLlm), which
# routes on a "<provider>/<model>" string and reads that provider's standard env
# vars. LLM_PROVIDER picks the backend; DEFAULT_MODEL names the model.
#
# Models are chosen PER AGENT, because the agents do very different work:
#
#     <AGENT>_MODEL  ->  WORKER_MODEL  ->  DEFAULT_MODEL
#
# The orchestrator plans, routes and merges, so it earns the capable model; the
# workers run bounded, well-scoped tasks and can run cheaper. A value that
# already contains "/" is passed to LiteLLM verbatim, so a single agent can be
# pointed at an entirely different provider without moving the others.
## =============================================================================

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()

# A sensible model per provider, used when DEFAULT_MODEL is unset. Empty means
# "you must set DEFAULT_MODEL yourself" (Azure needs the deployment name).
_PROVIDER_DEFAULT_MODEL = {
    "anthropic": "claude-haiku-4-5-20251001",
    "openai": "gpt-4o",
    "azure": "",
    "azure_ai": "",
    "gemini": "gemini-2.0-flash",
    "vertex_ai": "gemini-2.0-flash",
    "bedrock": "anthropic.claude-3-5-haiku-20241022-v1:0",
}

# Env vars each provider needs. LiteLLM reads them itself at call time; this map
# exists only so a misconfigured server fails fast and clearly at startup.
_PROVIDER_REQUIRED_ENV = {
    "anthropic": ["ANTHROPIC_API_KEY"],
    "openai": ["OPENAI_API_KEY"],
    "azure": ["AZURE_API_KEY", "AZURE_API_BASE"],
    "azure_ai": ["AZURE_AI_API_KEY", "AZURE_AI_API_BASE"],
    "gemini": ["GEMINI_API_KEY"],
    "vertex_ai": [],  # gcloud Application Default Credentials, checked by the SDK
    "bedrock": ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"],
}

SUPPORTED_LLM_PROVIDERS = tuple(_PROVIDER_REQUIRED_ENV)

DEFAULT_MODEL = (
    os.getenv("DEFAULT_MODEL", "").strip()
    or _PROVIDER_DEFAULT_MODEL.get(LLM_PROVIDER, "")
)

# Every agent that can have its own model. "orchestrator" is listed alongside the
# workers so one loop can validate them all.
AGENT_NAMES = ("orchestrator", "research", "data", "training", "evaluation")


def _agent_model_env(agent_name: str) -> str:
    """The `<AGENT>_MODEL` override for one agent, if set."""
    return os.getenv(f"{agent_name.upper()}_MODEL", "").strip()


def model_for_agent(agent_name: str = "worker") -> str:
    """The model name for one agent, before any provider prefixing.

    Resolution order: ``<AGENT>_MODEL`` -> ``WORKER_MODEL`` -> ``DEFAULT_MODEL``.
    """
    worker_default = os.getenv("WORKER_MODEL", "").strip()
    return _agent_model_env(agent_name) or worker_default or DEFAULT_MODEL


def _litellm_extra_kwargs() -> dict:
    """Provider kwargs LiteLLM wants passed explicitly rather than via env.

    Azure routing (deployment endpoint + api-version) is fiddly enough that we
    hand it to LiteLlm directly when the vars are present.
    """
    kw: dict = {}
    if LLM_PROVIDER == "azure":
        pairs = (("AZURE_API_BASE", "api_base"),
                 ("AZURE_API_VERSION", "api_version"),
                 ("AZURE_API_KEY", "api_key"))
    elif LLM_PROVIDER == "azure_ai":
        pairs = (("AZURE_AI_API_BASE", "api_base"),
                 ("AZURE_AI_API_VERSION", "api_version"),
                 ("AZURE_AI_API_KEY", "api_key"))
    elif LLM_PROVIDER == "anthropic":
        # lets you point the anthropic provider at an Anthropic-compatible
        # gateway (e.g. Azure AI Foundry's /anthropic endpoint) from .env
        pairs = (("ANTHROPIC_API_BASE", "api_base"),)
    else:
        pairs = ()
    for env_name, arg in pairs:
        val = os.getenv(env_name)
        if val:
            kw[arg] = val
    return kw


def get_llm_model(model: str | None = None, *, agent: str = "worker"):
    """A ``LiteLlm`` instance for one agent.

    Name resolution: an explicit ``model`` argument, else the agent's configured
    model (see :func:`model_for_agent`). A name that already carries a
    ``"<provider>/"`` prefix is used verbatim - the caller owns routing in that
    case, so LLM_PROVIDER's base/key kwargs are deliberately NOT attached (they
    would point at the wrong service).
    """
    from google.adk.models.lite_llm import LiteLlm

    name = (model or model_for_agent(agent) or "").strip()
    if not name:
        raise RuntimeError(
            f"No model configured for the {agent!r} agent "
            f"(LLM_PROVIDER={LLM_PROVIDER!r}). Set DEFAULT_MODEL in .env "
            f"(for Azure, that is the deployment name), or {agent.upper()}_MODEL."
        )
    if "/" in name:
        return LiteLlm(model=name)
    return LiteLlm(model=f"{LLM_PROVIDER}/{name}", **_litellm_extra_kwargs())


def missing_llm_credentials() -> list[str]:
    """Required env vars for the active LLM_PROVIDER that are not set."""
    return [v for v in _PROVIDER_REQUIRED_ENV.get(LLM_PROVIDER, []) if not os.getenv(v)]


def require_llm_credentials(agents: tuple[str, ...] = AGENT_NAMES) -> None:
    """Raise a clear error if the active provider can't be used. Call at startup."""
    if LLM_PROVIDER not in _PROVIDER_REQUIRED_ENV:
        raise RuntimeError(
            f"Unknown LLM_PROVIDER={LLM_PROVIDER!r}. "
            f"Supported: {', '.join(SUPPORTED_LLM_PROVIDERS)}."
        )
    missing = missing_llm_credentials()
    if missing:
        raise RuntimeError(
            f"LLM_PROVIDER={LLM_PROVIDER!r} needs {', '.join(missing)} set in .env "
            f"(or switch LLM_PROVIDER)."
        )
    for agent in agents:
        if not model_for_agent(agent):
            raise RuntimeError(
                f"No model for the {agent!r} agent (LLM_PROVIDER={LLM_PROVIDER!r}). "
                f"Set DEFAULT_MODEL (or {agent.upper()}_MODEL) in .env."
            )


## =============================================================================
# Agent servers - host and ports
#
# Each worker is an independent A2A server. The orchestrator is not in this map:
# it is an A2A *client* and runs under `adk web` / `adk api_server` on :8000.
## =============================================================================

AGENT_HOST = os.getenv("AGENT_HOST", "localhost")

WORKER_NAMES = ("research", "data", "training", "evaluation")

AGENT_PORTS = {
    "data": int(os.getenv("DATA_PORT", "10201")),
    "training": int(os.getenv("TRAINING_PORT", "10202")),
    "evaluation": int(os.getenv("EVALUATION_PORT", "10203")),
    "research": int(os.getenv("RESEARCH_PORT", "10204")),
}


def agent_url(agent_name: str) -> str:
    """Base URL for a worker agent ('research' | 'data' | 'training' | 'evaluation')."""
    try:
        port = AGENT_PORTS[agent_name]
    except KeyError:
        raise KeyError(
            f"Unknown worker {agent_name!r}; known workers: {', '.join(AGENT_PORTS)}"
        ) from None
    return f"http://{AGENT_HOST}:{port}"


## =============================================================================
# Agent roster
#
# The orchestrator does NOT hard-code which agents exist. It reads this roster,
# fetches each agent card, and routes on the advertised skills - so adding a new
# agent later is a config line, not an orchestrator change. Two sources, in
# precedence order: AUGUR_AGENT_REGISTRY (inline "name=url,name=url"), then
# AUGUR_AGENT_REGISTRY_FILE (a TOML file), then the built-in worker defaults.
## =============================================================================

AUGUR_AGENT_REGISTRY = os.getenv("AUGUR_AGENT_REGISTRY", "").strip()
AUGUR_AGENT_REGISTRY_FILE = os.getenv("AUGUR_AGENT_REGISTRY_FILE", "").strip()

# Whether the orchestrator may reach out to the workers on its own. Off (0) for
# the tests, which inject fakes; on everywhere else.
ORCHESTRATOR_AUTOINIT = os.getenv("AUGUR_ORCHESTRATOR_AUTOINIT", "1") != "0"


## =============================================================================
# Long-running work
#
# A training run can take hours or days, so a delegation must never be a blocking
# call that a restart would lose. The orchestrator dispatches an A2A task, stores
# the task id in its (DB-backed) workflow record, ends the turn, and advances
# when a later `get_task` poll - or a push notification to AUGUR_PUSH_URL -
# shows the task finished.
#
# A2A_CLIENT_TIMEOUT_SECONDS therefore bounds ONE message/send round trip, not a
# whole job, so it stays modest: a worker that is wedged should fail in minutes,
# not hold a socket open for a day.
## =============================================================================

AUGUR_PUSH_URL = os.getenv("AUGUR_PUSH_URL", "").strip()

A2A_CLIENT_TIMEOUT_SECONDS = float(os.getenv("A2A_CLIENT_TIMEOUT_SECONDS", "120"))
A2A_HEALTHCHECK_TIMEOUT_SECONDS = float(os.getenv("A2A_HEALTHCHECK_TIMEOUT_SECONDS", "5"))
A2A_MAX_RETRIES = int(os.getenv("A2A_MAX_RETRIES", "1"))
A2A_RETRY_BACKOFF_SECONDS = float(os.getenv("A2A_RETRY_BACKOFF_SECONDS", "1.5"))


## =============================================================================
# Session / workflow storage
#
#   "memory"   -> InMemorySessionService   (fast, zero setup, lost on restart)
#   "database" -> DatabaseSessionService   (survives a restart)
#
# The ORCHESTRATOR should run on "database": its lifecycle record has to outlive
# the process while a training job runs. Workers are fine in memory. The service
# objects are built in persistence.py so importing this module never needs
# SQLAlchemy.
## =============================================================================

SESSION_BACKEND = os.getenv("SESSION_BACKEND", "memory").strip().lower()

_DEFAULT_DB_PATH = str(REPO_ROOT / "augur_agents.db").replace("\\", "/")
SESSION_DB_URL = os.getenv("SESSION_DB_URL", f"sqlite+aiosqlite:///{_DEFAULT_DB_PATH}")


## =============================================================================
# Stub tool behaviour
#
# There are no MCP tool servers and no GPUs behind these agents yet; the tools
# return realistic mock data so the whole pipeline runs end to end. These knobs
# only affect that stub layer and disappear with it.
## =============================================================================

# How long a stub training job takes to reach COMPLETED. Small so the demo
# finishes; raise it to watch the orchestrator poll a job that really is still
# running, which is the behaviour that matters for real multi-hour runs.
STUB_TRAINING_DURATION_SECONDS = float(os.getenv("STUB_TRAINING_DURATION_SECONDS", "20"))

# The stub job store. A tiny SQLite file rather than a dict, so a submitted job
# survives a worker restart - this is the seam a real training-mcp job manager
# replaces, and keeping it durable now means the polling path is honest.
_DEFAULT_JOB_DB_PATH = str(REPO_ROOT / "augur_jobs.db").replace("\\", "/")
JOB_STORE_URL = os.getenv("AUGUR_JOB_STORE_URL", f"sqlite:///{_DEFAULT_JOB_DB_PATH}")


