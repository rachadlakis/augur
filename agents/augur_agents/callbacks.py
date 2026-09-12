"""ADK lifecycle callbacks shared by every agent.

Scope is deliberately narrow - observability only:

1. **One structured line per tool call** (`which agent -> which tool(args)`, then
   duration and ok/FAILED). Without this a slow delegation is a black box: when
   the orchestrator sits waiting on the training agent you want the log to say
   which tool it is inside, not just that nothing is happening.
2. **Token usage per model turn**, which is cheap cost visibility now and the
   hook a per-tenant metering build would extend later.

Callbacks here never raise - a logging bug must not fail a request - and they
never rewrite a model or tool result.

Deliberately NOT added: content filtering or response rewriting. Those suit a
public chatbot; this is an internal control plane where silently altering a tool
result would undermine the audit trail.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from google.adk.tools.base_tool import BaseTool

logger = logging.getLogger("augur.agents")

# function_call_id -> monotonic start time. Module level because there is one OS
# process per agent server, so tool timing never has to be written into session
# state (and therefore never hits the database). after_tool pops its entry; a
# tool that dies before after_tool runs leaks one float, which is negligible.
_tool_starts: dict[str, float] = {}


def _short_args(args: dict[str, Any], limit: int = 160) -> str:
    text = ", ".join(f"{k}={v!r}" for k, v in (args or {}).items())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _call_key(ctx: Any) -> str:
    return getattr(ctx, "function_call_id", None) or getattr(ctx, "invocation_id", "?")


def log_before_tool(
    tool: BaseTool, args: dict[str, Any], tool_context: Any
) -> Optional[dict]:
    """Record the start time and log the call. Never blocks the tool."""
    try:
        _tool_starts[_call_key(tool_context)] = time.monotonic()
        agent = getattr(tool_context, "agent_name", "?")
        logger.info("[tool] %s -> %s(%s)", agent, tool.name, _short_args(args))
    except Exception:  # pragma: no cover - logging must not break a request
        logger.debug("log_before_tool failed", exc_info=True)
    return None


def log_after_tool(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: Any,
    tool_response: Any,
) -> Optional[dict]:
    """Log duration and outcome. Returns None: never rewrites the response."""
    try:
        start = _tool_starts.pop(_call_key(tool_context), None)
        secs = f"{time.monotonic() - start:.1f}s" if start is not None else "?"
        agent = getattr(tool_context, "agent_name", "?")
        # Our tools signal failure in-band with success=False rather than
        # raising, so a "failed" call still arrives here as a normal response.
        failed = isinstance(tool_response, dict) and tool_response.get("success") is False
        if failed:
            logger.warning(
                "[tool] %s <- %s %s FAILED: %s",
                agent, tool.name, secs, tool_response.get("error", ""),
            )
        else:
            logger.info("[tool] %s <- %s %s ok", agent, tool.name, secs)
    except Exception:  # pragma: no cover
        logger.debug("log_after_tool failed", exc_info=True)
    return None


def log_after_model(callback_context: Any, llm_response: Any) -> None:
    """Log token usage for the turn."""
    try:
        usage = getattr(llm_response, "usage_metadata", None)
        if usage is not None:
            logger.info(
                "[model] %s tokens prompt=%s output=%s total=%s",
                getattr(callback_context, "agent_name", "?"),
                getattr(usage, "prompt_token_count", "?"),
                getattr(usage, "candidates_token_count", "?"),
                getattr(usage, "total_token_count", "?"),
            )
    except Exception:  # pragma: no cover
        logger.debug("log_after_model failed", exc_info=True)
    return None


# Spread into every LlmAgent(...): the before_*/after_* hooks accept a list, and
# list order is execution order.
AGENT_CALLBACKS: dict[str, Any] = {
    "before_tool_callback": [log_before_tool],
    "after_tool_callback": [log_after_tool],
    "after_model_callback": [log_after_model],
}


def configure_logging(level: int = logging.INFO) -> None:
    """Sensible console logging for a worker process.

    Also silences ADK's `[EXPERIMENTAL]` A2A warnings: they fire on every
    `to_a2a` / executor construction and would otherwise bury the tool lines
    that actually tell you what an agent is doing.
    """
    import warnings

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    warnings.filterwarnings("ignore", message=r".*\[EXPERIMENTAL\].*")


__all__ = [
    "log_before_tool",
    "log_after_tool",
    "log_after_model",
    "AGENT_CALLBACKS",
    "configure_logging",
]
