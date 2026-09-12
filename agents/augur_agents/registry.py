"""Who the orchestrator can talk to.

The orchestrator does not hard-code its workers. It asks this module for a
roster of ``(name, base_url)`` pairs, fetches each agent's card, and routes on
the *advertised skills*. Adding a sixth agent later is a line of config, not an
orchestrator change - which is the whole point of putting A2A at this boundary.

Sources, in precedence order:

1. ``AUGUR_AGENT_REGISTRY`` - inline ``"name=url,name=url"``.
2. ``AUGUR_AGENT_REGISTRY_FILE`` - a TOML file (see :func:`from_toml`).
3. The built-in workers in ``config.AGENT_PORTS``.

A malformed entry is skipped with a warning rather than taking the process down:
one bad line in a roster should not stop the other agents from being reachable.
"""

from __future__ import annotations

import logging
from pathlib import Path

import tomllib

from augur_agents import config

logger = logging.getLogger("augur.agents.registry")


class AgentEndpoint:
    """One entry in the roster: a name and where to reach it."""

    __slots__ = ("name", "url")

    def __init__(self, name: str, url: str) -> None:
        self.name = name
        self.url = url.rstrip("/")

    @property
    def card_url(self) -> str:
        return f"{self.url}/.well-known/agent-card.json"

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"AgentEndpoint({self.name!r}, {self.url!r})"

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, AgentEndpoint)
            and (self.name, self.url) == (other.name, other.url)
        )


def _parse_inline(raw: str) -> list[AgentEndpoint]:
    """``"data=http://host:1,training=http://host:2"`` -> endpoints."""
    out: list[AgentEndpoint] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        name, sep, url = chunk.partition("=")
        name, url = name.strip(), url.strip()
        if not sep or not name or not url:
            logger.warning("registry: skipping malformed entry %r (want name=url)", chunk)
            continue
        out.append(AgentEndpoint(name, url))
    return out


def from_toml(path: str | Path) -> list[AgentEndpoint]:
    """Read a roster file.

    Accepts either shape::

        [agents]
        data = "http://localhost:10201"

        # or
        [[agent]]
        name = "data"
        url  = "http://localhost:10201"
    """
    p = Path(path)
    if not p.is_absolute():
        p = config.REPO_ROOT / p
    if not p.exists():
        logger.warning("registry: %s does not exist, ignoring", p)
        return []
    try:
        data = tomllib.loads(p.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        logger.warning("registry: could not read %s: %s", p, exc)
        return []

    out: list[AgentEndpoint] = []
    for name, url in (data.get("agents") or {}).items():
        if isinstance(url, str) and url.strip():
            out.append(AgentEndpoint(str(name), url))
        else:
            logger.warning("registry: skipping %r in %s (url must be a string)", name, p)
    for entry in data.get("agent") or []:
        name, url = entry.get("name"), entry.get("url")
        if name and url:
            out.append(AgentEndpoint(str(name), str(url)))
        else:
            logger.warning("registry: skipping %r in %s (needs name and url)", entry, p)
    return out


def default_roster() -> list[AgentEndpoint]:
    """The built-in workers, from the configured ports."""
    return [AgentEndpoint(name, config.agent_url(name)) for name in config.WORKER_NAMES]


def load_roster() -> list[AgentEndpoint]:
    """The active roster. Duplicate names resolve to the first occurrence."""
    endpoints: list[AgentEndpoint]
    if config.AUGUR_AGENT_REGISTRY:
        endpoints = _parse_inline(config.AUGUR_AGENT_REGISTRY)
        source = "AUGUR_AGENT_REGISTRY"
    elif config.AUGUR_AGENT_REGISTRY_FILE:
        endpoints = from_toml(config.AUGUR_AGENT_REGISTRY_FILE)
        source = config.AUGUR_AGENT_REGISTRY_FILE
    else:
        endpoints = default_roster()
        source = "built-in defaults"

    seen: dict[str, AgentEndpoint] = {}
    for ep in endpoints:
        if ep.name in seen:
            logger.warning("registry: duplicate agent %r, keeping the first", ep.name)
            continue
        seen[ep.name] = ep

    if not seen:
        logger.warning("registry: %s produced no agents", source)
    else:
        logger.info(
            "registry: %d agent(s) from %s: %s",
            len(seen), source, ", ".join(seen),
        )
    return list(seen.values())


__all__ = ["AgentEndpoint", "load_roster", "default_roster", "from_toml"]

