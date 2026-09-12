"""Serving one worker agent over A2A.

Every worker is an ordinary ADK ``LlmAgent`` wrapped by ADK's own A2A
integration (``to_a2a``), which builds the Starlette app, the executor, and the
task store. We do not hand-roll an ``A2AStarletteApplication``.

**Why the card is built, not constructed.** In a2a-sdk 1.x ``a2a.types`` is
protobuf-backed and ``AgentCard`` has no ``url`` field - it carries
``supported_interfaces`` entries instead. Writing a card literal the 0.3.x way
fails at import with *"Protocol message AgentCard has no url field"*. ADK's
``AgentCardBuilder`` knows both shapes, so we let it build and then replace the
one thing it gets wrong for us: its auto-derived skill is a generic
``{id: <agent name>, name: "model", tags: ["llm"]}``, which tells the
orchestrator nothing useful to route on.
"""

from __future__ import annotations

import asyncio
import logging

from a2a.types import AgentCapabilities, AgentSkill
from google.adk.a2a.utils.agent_card_builder import AgentCardBuilder
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from google.adk.agents import BaseAgent

from augur_agents import config

logger = logging.getLogger("augur.agents.a2a_server")


def build_skill(
    *,
    skill_id: str,
    name: str,
    description: str,
    tags: list[str],
    examples: list[str],
) -> AgentSkill:
    """One advertised capability.

    A *skill* is the outward advertisement other agents route on; the agent's
    internal tool list is not part of the card. Keep the description concrete
    about what this agent will and will not do - the orchestrator picks an agent
    from these strings alone.
    """
    return AgentSkill(
        id=skill_id,
        name=name,
        description=description,
        tags=list(tags),
        examples=list(examples),
    )


async def build_card(
    agent: BaseAgent,
    *,
    skill: AgentSkill,
    port: int,
    host: str | None = None,
    version: str = "1.0.0",
    description: str | None = None,
):
    """An A2A ``AgentCard`` for one worker, with our skill rather than ADK's.

    ``push_notifications`` is advertised because the orchestrator may register a
    webhook so a long task can announce completion instead of being polled.
    """
    host = host or config.AGENT_HOST
    builder = AgentCardBuilder(
        agent=agent,
        rpc_url=f"http://{host}:{port}/",
        agent_version=version,
        capabilities=AgentCapabilities(streaming=True, push_notifications=True),
    )
    card = await builder.build()

    # Protobuf repeated field: clear then extend, rather than assigning.
    del card.skills[:]
    card.skills.append(skill)
    if description:
        card.description = description
    return card


def build_server(
    agent: BaseAgent,
    *,
    skill: AgentSkill,
    port: int,
    host: str | None = None,
    version: str = "1.0.0",
    description: str | None = None,
):
    """A Starlette app serving ``agent`` over A2A. Sync wrapper for the CLI.

    Serves ``POST /`` (JSON-RPC ``message/send``, ``tasks/get``, ...) and
    ``GET /.well-known/agent-card.json``.
    """
    host = host or config.AGENT_HOST
    card = asyncio.run(
        build_card(
            agent, skill=skill, port=port, host=host,
            version=version, description=description,
        )
    )
    logger.info("serving %s on http://%s:%d/ (skill: %s)", card.name, host, port, skill.id)
    return to_a2a(agent, host=host, port=port, agent_card=card)


__all__ = ["build_skill", "build_card", "build_server"]

