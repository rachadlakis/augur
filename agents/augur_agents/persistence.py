"""Session storage for the agents.

Every ADK ``Runner`` needs a ``session_service``. This hands one back based on
``SESSION_BACKEND``:

    SESSION_BACKEND=memory     -> InMemorySessionService   (default)
    SESSION_BACKEND=database   -> DatabaseSessionService(SESSION_DB_URL)

**The orchestrator should run on the database backend.** Its workflow record is
what survives while a multi-hour training job runs; with in-memory sessions, a
restart loses the record and there is nothing left that knows which A2A task to
poll. Workers are stateless enough to stay in memory.

The service is built once per process and cached, so several runners in one
process share a connection pool.

Note: ``adk api_server`` / ``adk web`` build their *own* session service and
take ``--session_service_uri`` instead of reading ``SESSION_BACKEND``. This
module governs the paths where this codebase builds the ``Runner`` itself (the
worker servers via ``to_a2a``, and any future standalone orchestrator server).
"""

from __future__ import annotations

import logging

from augur_agents.config import SESSION_BACKEND, SESSION_DB_URL

logger = logging.getLogger("augur.agents.persistence")

_MEMORY_ALIASES = {"memory", "in_memory", "inmemory", "in-memory"}
_DATABASE_ALIASES = {"database", "db", "sqlite", "postgres", "postgresql"}

_session_service = None

# ADK's DatabaseSessionService runs on SQLAlchemy's *async* engine, which rejects
# sync drivers. Upgrade the common sync URLs so a plain "sqlite:///..." in .env
# just works instead of failing with an opaque driver error.
_ASYNC_DRIVER_UPGRADES = {
    "sqlite://": "sqlite+aiosqlite://",
    "postgresql://": "postgresql+asyncpg://",
    "postgres://": "postgresql+asyncpg://",
    "mysql://": "mysql+aiomysql://",
}


def async_db_url(url: str) -> str:
    """Rewrite a sync SQLAlchemy URL to its async driver.

    URLs that already name a driver (``sqlite+aiosqlite://``) are left alone.
    """
    for sync_prefix, async_prefix in _ASYNC_DRIVER_UPGRADES.items():
        if url.startswith(sync_prefix):
            return async_prefix + url[len(sync_prefix):]
    return url


def _build_session_service():
    backend = SESSION_BACKEND

    if backend in _DATABASE_ALIASES:
        from google.adk.sessions import DatabaseSessionService

        db_url = async_db_url(SESSION_DB_URL)
        logger.info("session backend: database (%s)", db_url)
        return DatabaseSessionService(db_url=db_url)

    if backend not in _MEMORY_ALIASES:
        logger.warning(
            "unknown SESSION_BACKEND=%r; falling back to in-memory sessions.", backend
        )
    else:
        logger.info("session backend: in-memory (sessions are lost on restart)")

    from google.adk.sessions import InMemorySessionService

    return InMemorySessionService()


def get_session_service():
    """The process-wide session service (cached after the first call)."""
    global _session_service
    if _session_service is None:
        _session_service = _build_session_service()
    return _session_service


def reset_session_service() -> None:
    """Drop the cached service. Tests only."""
    global _session_service
    _session_service = None


__all__ = ["get_session_service", "reset_session_service", "async_db_url"]

