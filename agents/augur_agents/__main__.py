"""Serve the worker agents.

    python -m augur_agents serve research      # one worker
    python -m augur_agents serve all           # all four, as subprocesses
    python -m augur_agents list                # the roster and ports

The orchestrator is not served here - it is an A2A *client*, and runs under
`adk web` / `adk api_server`:

    adk api_server --with_ui --port 8000 agents/augur_agents
"""

from __future__ import annotations

import argparse
import importlib
import logging
import subprocess
import sys
import time

import uvicorn

from augur_agents import config, registry
from augur_agents.a2a_server import build_server
from augur_agents.callbacks import configure_logging

logger = logging.getLogger("augur.agents.serve")

WORKERS = ("research", "data", "training", "evaluation")


def _load(worker: str):
    """Import one worker's agent module (lazily - do not import all four)."""
    return importlib.import_module(f"augur_agents.{worker}.agent")


def serve_one(worker: str) -> int:
    """Run one worker's A2A server in this process."""
    if worker not in WORKERS:
        logger.error("unknown worker %r; expected one of %s", worker, ", ".join(WORKERS))
        return 2

    configure_logging()
    missing = config.missing_llm_credentials()
    if missing:
        logger.error(
            "LLM_PROVIDER=%s needs %s set in .env (or change LLM_PROVIDER).",
            config.LLM_PROVIDER, ", ".join(missing),
        )
        return 1

    module = _load(worker)
    port = config.AGENT_PORTS[worker]
    logger.info(
        "%s using model %r", worker, config.model_for_agent(worker) or "(unset)"
    )
    app = build_server(
        module.create_agent(),
        skill=module.build_card_skill(),
        port=port,
        description=module.DESCRIPTION,
    )
    uvicorn.run(app, host=config.AGENT_HOST, port=port, log_level="warning")
    return 0


def serve_all() -> int:
    """Run every worker as a subprocess, and shut them down together."""
    configure_logging()
    procs: list[tuple[str, subprocess.Popen]] = []
    print("Starting workers...")
    print("-" * 52)
    for worker in WORKERS:
        proc = subprocess.Popen(
            [sys.executable, "-m", "augur_agents", "serve", worker]
        )
        procs.append((worker, proc))
        print(f"  {worker:<12} http://{config.AGENT_HOST}:{config.AGENT_PORTS[worker]}")
    print("-" * 52)
    print(f"{len(procs)} workers running. Ctrl+C to stop them all.\n")

    reported: set[str] = set()
    try:
        while True:
            time.sleep(1)
            for name, proc in procs:
                if proc.poll() is not None and name not in reported:
                    reported.add(name)
                    print(f"WARNING: {name} exited (code {proc.returncode})")
            if len(reported) == len(procs):
                print("All workers exited.")
                return 1
    except KeyboardInterrupt:
        print("\nStopping workers...")
        for _, proc in procs:
            proc.terminate()
        for _, proc in procs:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        print("Stopped.")
        return 0


def list_agents() -> int:
    """Print the roster the orchestrator will use."""
    print(f"LLM provider : {config.LLM_PROVIDER}")
    print(f"Default model: {config.DEFAULT_MODEL or '(unset)'}\n")
    print(f"{'agent':<14}{'port':<8}{'model':<38}url")
    print("-" * 96)
    for ep in registry.load_roster():
        port = config.AGENT_PORTS.get(ep.name, "-")
        model = config.model_for_agent(ep.name) or "(unset)"
        print(f"{ep.name:<14}{str(port):<8}{model:<38}{ep.url}")
    print(
        f"\n{'orchestrator':<14}{'8000':<8}"
        f"{config.model_for_agent('orchestrator') or '(unset)':<38}"
        "adk api_server --with_ui --port 8000 agents/augur_agents"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m augur_agents",
        description="Serve the Augur Tensors worker agents.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="run a worker (or 'all')")
    serve.add_argument("worker", choices=(*WORKERS, "all"))

    sub.add_parser("list", help="show the roster, ports and per-agent models")

    args = parser.parse_args(argv)
    if args.command == "list":
        return list_agents()
    return serve_all() if args.worker == "all" else serve_one(args.worker)


if __name__ == "__main__":
    raise SystemExit(main())


