"""The orchestrator's side of the A2A wire.

This is the layer that lets the orchestrator **drive without handing off**. It
never returns an ADK agent to be delegated to; it returns plain dicts that the
orchestrator reads as ordinary tool results and then keeps reasoning.

Three things it has to get right:

**1. Discovery is lazy and forgiving.** Agents are looked up from the roster
(``registry.py``), their cards fetched on first use and cached. A worker that
was down is simply retried next time, so start order never matters and a missing
agent degrades the answer instead of killing the process.

**2. A delegation must be able to outlive the call.** ``dispatch_task`` streams
the worker's task and stops as soon as either the task reaches a terminal state
*or* our own patience budget expires - and in the second case it still returns
the ``task_id`` in ``working`` state. The orchestrator stores that id, ends its
turn, and picks the task back up later with :func:`get_task`. Nothing holds a
socket open for a job that runs for hours.

**3. Failure is data, not an exception.** Every function returns
``{"success": bool, ...}``. A worker that is down produces a readable ``error``
the orchestrator can route around ("deliver what the others returned, say which
part is missing") rather than a traceback that takes the whole turn down.

a2a-sdk 1.x notes: ``a2a.types`` is protobuf, ``A2AClient`` no longer exists
(it is ``ClientFactory(...).create(card)``), and ``Client.send_message`` is an
async *generator* of ``StreamResponse``, not a coroutine returning one reply.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

import httpx
from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
from a2a.types import GetTaskRequest, Message, Part, Role, SendMessageRequest, TaskState

from augur_agents import config, registry

logger = logging.getLogger("augur.agents.a2a_client")

# HTTP statuses worth one retry: the worker is probably restarting.
_TRANSIENT_HTTP_STATUS = {502, 503, 504}

_STATE_ALIASES = {
    "completed": (getattr(TaskState, "TASK_STATE_COMPLETED", None), getattr(TaskState, "COMPLETED", None)),
    "failed": (getattr(TaskState, "TASK_STATE_FAILED", None), getattr(TaskState, "FAILED", None)),
    "canceled": (getattr(TaskState, "TASK_STATE_CANCELED", None), getattr(TaskState, "CANCELED", None)),
    "rejected": (getattr(TaskState, "TASK_STATE_REJECTED", None), getattr(TaskState, "REJECTED", None)),
    "submitted": (getattr(TaskState, "TASK_STATE_SUBMITTED", None), getattr(TaskState, "SUBMITTED", None)),
    "working": (getattr(TaskState, "TASK_STATE_WORKING", None), getattr(TaskState, "WORKING", None)),
    "input_required": (getattr(TaskState, "TASK_STATE_INPUT_REQUIRED", None), getattr(TaskState, "INPUT_REQUIRED", None)),
    "auth_required": (getattr(TaskState, "TASK_STATE_AUTH_REQUIRED", None), getattr(TaskState, "AUTH_REQUIRED", None)),
}

_TERMINAL_STATES = {
    v for variants in _STATE_ALIASES.values() for v in variants if v is not None
} & {
    getattr(TaskState, "TASK_STATE_COMPLETED", None),
    getattr(TaskState, "COMPLETED", None),
    getattr(TaskState, "TASK_STATE_FAILED", None),
    getattr(TaskState, "FAILED", None),
    getattr(TaskState, "TASK_STATE_CANCELED", None),
    getattr(TaskState, "CANCELED", None),
    getattr(TaskState, "TASK_STATE_REJECTED", None),
    getattr(TaskState, "REJECTED", None),
}

# States where the worker is waiting on us; the task stays open.
_OPEN_STATES = {
    getattr(TaskState, "TASK_STATE_SUBMITTED", None),
    getattr(TaskState, "SUBMITTED", None),
    getattr(TaskState, "TASK_STATE_WORKING", None),
    getattr(TaskState, "WORKING", None),
    getattr(TaskState, "TASK_STATE_INPUT_REQUIRED", None),
    getattr(TaskState, "INPUT_REQUIRED", None),
    getattr(TaskState, "TASK_STATE_AUTH_REQUIRED", None),
    getattr(TaskState, "AUTH_REQUIRED", None),
}


def state_name(state: Any) -> str:
    """Normalize the A2A task-state enum to a simple lowercase name."""
    if state is None:
        return "unknown"
    if isinstance(state, str):
        return state.removeprefix("TASK_STATE_").lower()
    if hasattr(state, "name"):
        raw = state.name
    else:
        try:
            raw = TaskState.Name(state)
        except (ValueError, TypeError, AttributeError):
            return str(state)
    return raw.removeprefix("TASK_STATE_").lower()


def _artifact_text(task: Any) -> str:
    """Concatenate the text parts a worker returned.

    File parts are noted rather than inlined: the orchestrator's context should
    never receive base64 bytes.
    """
    chunks: list[str] = []
    for artifact in getattr(task, "artifacts", None) or []:
        for part in getattr(artifact, "parts", None) or []:
            if part.text:
                chunks.append(part.text)
            elif part.filename:
                chunks.append(f"[file: {part.filename} ({part.media_type or 'unknown'})]")
    return "\n".join(c for c in chunks if c).strip()


def _task_payload(task: Any, agent_name: str) -> dict[str, Any]:
    """The dict shape every task-returning function hands back."""
    state = task.status.state
    return {
        "success": True,
        "agent": agent_name,
        "task_id": task.id,
        "context_id": task.context_id or None,
        "state": state_name(state),
        "is_terminal": state in _TERMINAL_STATES,
        "result": _artifact_text(task),
    }


def _error(agent_name: str, message: str, **extra: Any) -> dict[str, Any]:
    logger.warning("a2a: %s", message)
    return {"success": False, "agent": agent_name, "error": message, **extra}


class AgentDirectory:
    """Discovers workers and talks to them. One instance per orchestrator process."""

    def __init__(self, endpoints: list[registry.AgentEndpoint] | None = None) -> None:
        self._endpoints = {
            ep.name: ep for ep in (endpoints if endpoints is not None else registry.load_roster())
        }
        self._cards: dict[str, Any] = {}
        self._httpx: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()

    ## -------------------------------------------------------------------- ##
    ## Plumbing
    ## -------------------------------------------------------------------- ##

    def _client_pool(self) -> httpx.AsyncClient:
        if self._httpx is None or self._httpx.is_closed:
            timeout = httpx.Timeout(
                config.A2A_CLIENT_TIMEOUT_SECONDS,
                connect=10.0,
                write=30.0,
                pool=config.A2A_CLIENT_TIMEOUT_SECONDS,
            )
            self._httpx = httpx.AsyncClient(timeout=timeout)
        return self._httpx

    async def aclose(self) -> None:
        if self._httpx is not None and not self._httpx.is_closed:
            await self._httpx.aclose()

    async def _is_reachable(self, endpoint: registry.AgentEndpoint) -> bool:
        """Cheap liveness probe so a dead worker fails in seconds.

        Without it a wedged worker would block for the full request timeout
        before the orchestrator learned anything was wrong.
        """
        if config.A2A_HEALTHCHECK_TIMEOUT_SECONDS <= 0:
            return True
        try:
            async with httpx.AsyncClient(
                timeout=config.A2A_HEALTHCHECK_TIMEOUT_SECONDS
            ) as probe:
                resp = await probe.get(endpoint.card_url)
            return resp.status_code < 500
        except Exception:
            return False

    async def _card(self, agent_name: str):
        """The cached agent card, fetching it on first use."""
        if agent_name in self._cards:
            return self._cards[agent_name]
        endpoint = self._endpoints.get(agent_name)
        if endpoint is None:
            raise KeyError(agent_name)
        async with self._lock:
            if agent_name in self._cards:  # another task won the race
                return self._cards[agent_name]
            resolver = A2ACardResolver(self._client_pool(), endpoint.url)
            card = await resolver.get_agent_card()
            self._cards[agent_name] = card
            logger.info("discovered %s at %s", agent_name, endpoint.url)
            return card

    def _make_client(self, card):
        factory = ClientFactory(
            ClientConfig(
                httpx_client=self._client_pool(),
                # Streaming, so we see the task id as soon as it exists rather
                # than only when the whole turn is finished. That is what makes
                # a slow delegation resumable instead of all-or-nothing.
                streaming=True,
                polling=False,
            )
        )
        return factory.create(card)

    ## -------------------------------------------------------------------- ##
    ## Discovery
    ## -------------------------------------------------------------------- ##

    async def list_agents(self) -> list[dict[str, Any]]:
        """Every reachable agent and what it advertises.

        Unreachable agents are included with ``available: False`` so the
        orchestrator can say "the evaluation agent is down" instead of silently
        pretending that capability never existed.
        """
        out: list[dict[str, Any]] = []
        for name, endpoint in self._endpoints.items():
            try:
                card = await self._card(name)
            except Exception as exc:
                out.append({
                    "name": name,
                    "available": False,
                    "url": endpoint.url,
                    "error": f"{type(exc).__name__}: {exc}",
                })
                continue
            out.append({
                "name": name,
                "available": True,
                "url": endpoint.url,
                "description": card.description,
                "skills": [
                    {
                        "id": s.id,
                        "name": s.name,
                        "description": s.description,
                        "examples": list(s.examples),
                    }
                    for s in card.skills
                ],
            })
        return out

    ## -------------------------------------------------------------------- ##
    ## Delegation
    ## -------------------------------------------------------------------- ##

    async def dispatch_task(
        self,
        agent_name: str,
        instruction: str,
        *,
        context_id: str | None = None,
        task_id: str | None = None,
        wait_seconds: float | None = None,
    ) -> dict[str, Any]:
        """Send a sub-task to a worker and return as soon as we reasonably can.

        Returns a terminal payload if the worker finished inside
        ``wait_seconds``; otherwise a ``working`` payload carrying the
        ``task_id`` so the caller can poll later. Either way the caller gets a
        dict, never an exception.

        ``task_id`` continues an already-open task (e.g. answering an
        ``input_required``); omit it to start a fresh one. Task ids are
        per-agent - passing one agent's id to another is meaningless and the
        server will reject it.
        """
        if agent_name not in self._endpoints:
            return _error(
                agent_name,
                f"Unknown agent {agent_name!r}. Known agents: "
                f"{', '.join(sorted(self._endpoints)) or '(none configured)'}.",
            )
        endpoint = self._endpoints[agent_name]
        budget = wait_seconds if wait_seconds is not None else config.A2A_CLIENT_TIMEOUT_SECONDS

        if not await self._is_reachable(endpoint):
            return _error(
                agent_name,
                f"{agent_name} is not responding to a health check (waited "
                f"{config.A2A_HEALTHCHECK_TIMEOUT_SECONDS:.0f}s) - it looks down "
                f"or is restarting.",
            )

        attempts = max(1, config.A2A_MAX_RETRIES + 1)
        last_error = "unknown error"
        for attempt in range(attempts):
            try:
                return await self._send_once(
                    agent_name, instruction,
                    context_id=context_id, task_id=task_id, budget=budget,
                )
            except httpx.TimeoutException:
                # Retrying would just time out again.
                return _error(
                    agent_name,
                    f"{agent_name} did not respond within "
                    f"{config.A2A_CLIENT_TIMEOUT_SECONDS:.0f}s.",
                )
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                last_error = f"HTTP {status} from {agent_name}"
                transient = status in _TRANSIENT_HTTP_STATUS
            except Exception as exc:  # noqa: BLE001 - a delegation must not crash the turn
                last_error = f"{type(exc).__name__} talking to {agent_name}: {exc}"
                transient = isinstance(exc, (httpx.ConnectError, httpx.ReadError))

            if not transient or attempt == attempts - 1:
                break
            backoff = config.A2A_RETRY_BACKOFF_SECONDS * (2**attempt)
            logger.info("transient error (%s); retrying %s in %.1fs",
                        last_error, agent_name, backoff)
            await asyncio.sleep(backoff)

        return _error(agent_name, f"Delegation to {agent_name} failed: {last_error}.")

    async def _send_once(
        self,
        agent_name: str,
        instruction: str,
        *,
        context_id: str | None,
        task_id: str | None,
        budget: float,
    ) -> dict[str, Any]:
        card = await self._card(agent_name)
        client = self._make_client(card)

        message = Message(
            message_id=uuid.uuid4().hex,
            role=Role.ROLE_USER,
            parts=[Part(text=instruction)],
        )
        if context_id:
            message.context_id = context_id
        if task_id:
            message.task_id = task_id

        request = SendMessageRequest(message=message)

        deadline = time.monotonic() + budget
        latest: Any = None
        async for event in client.send_message(request):
            # StreamResponse is a oneof: task | message | status_update |
            # artifact_update. We only need whichever carries a task.
            task = None
            which = event.WhichOneof("payload")
            if which == "task":
                task = event.task
            elif which == "status_update" and event.status_update.task_id:
                # A status update tells us the id and state but not artifacts;
                # remember it so a timeout still yields something useful.
                if latest is None:
                    latest = {
                        "success": True,
                        "agent": agent_name,
                        "task_id": event.status_update.task_id,
                        "context_id": event.status_update.context_id or None,
                        "state": state_name(event.status_update.status.state),
                        "is_terminal": event.status_update.status.state in _TERMINAL_STATES,
                        "result": "",
                    }
                else:
                    latest["state"] = state_name(event.status_update.status.state)
                    latest["is_terminal"] = (
                        event.status_update.status.state in _TERMINAL_STATES
                    )
                continue

            if task is not None:
                latest = _task_payload(task, agent_name)
                if task.status.state in _TERMINAL_STATES:
                    return latest

            if time.monotonic() > deadline:
                # Out of patience, but the work is still going. Hand back the
                # task id so the orchestrator can pick it up on a later turn -
                # this is the path a multi-hour job takes.
                if latest is not None:
                    latest["timed_out_waiting"] = True
                    latest["note"] = (
                        f"{agent_name} is still working. Poll get_task with "
                        f"task_id={latest['task_id']!r} on a later turn."
                    )
                    return latest
                break

        if latest is not None:
            return latest
        return _error(agent_name, f"{agent_name} returned no usable task.")

    async def get_task(self, agent_name: str, task_id: str) -> dict[str, Any]:
        """Poll a task the orchestrator dispatched earlier.

        This is how the orchestrator "waits" for hours of work without holding
        anything open: it asks again on a later turn.
        """
        if agent_name not in self._endpoints:
            return _error(agent_name, f"Unknown agent {agent_name!r}.")
        try:
            card = await self._card(agent_name)
            client = self._make_client(card)
            task = await client.get_task(GetTaskRequest(id=task_id))
        except Exception as exc:  # noqa: BLE001
            return _error(
                agent_name,
                f"could not read task {task_id!r} from {agent_name}: "
                f"{type(exc).__name__}: {exc}",
                task_id=task_id,
            )
        return _task_payload(task, agent_name)


_directory: AgentDirectory | None = None


def get_directory() -> AgentDirectory:
    """The process-wide directory (cached)."""
    global _directory
    if _directory is None:
        _directory = AgentDirectory()
    return _directory


def reset_directory() -> None:
    """Drop the cached directory. Tests only."""
    global _directory
    _directory = None


__all__ = [
    "AgentDirectory",
    "get_directory",
    "reset_directory",
    "state_name",
]

