"""Every agent builds, and every worker serves a valid card.

No LLM calls: `create_agent()` constructs an `LlmAgent` without contacting a
provider, and the card is served by an in-process Starlette test client.
"""

from __future__ import annotations

import importlib

import pytest
from starlette.testclient import TestClient

from augur_agents import config
from augur_agents.a2a_server import build_server

WORKERS = ("research", "data", "training", "evaluation")

EXPECTED_TOOLS = {
    "research": {"search_papers", "get_paper", "summarize_findings"},
    "data": {"inspect_dataset", "validate_dataset", "materialize_dataset",
             "build_manifest", "list_datasets"},
    "training": {"recommend_parallelism", "validate_training_plan",
                 "estimate_training_job", "submit_training_job",
                 "get_training_status", "cancel_training_job", "resume_training_job"},
    "evaluation": {"run_evaluation", "get_evaluation_report", "compare_candidates",
                   "list_suites"},
}

EXPECTED_SKILL = {
    "research": "literature_research",
    "data": "dataset_curation",
    "training": "model_training",
    "evaluation": "model_evaluation",
}


@pytest.fixture(params=WORKERS)
def worker(request):
    return request.param


def _module(worker: str):
    return importlib.import_module(f"augur_agents.{worker}.agent")


class TestAgentsBuild:
    def test_create_agent_builds_an_llm_agent_with_the_right_tools(self, worker):
        agent = _module(worker).create_agent()
        tool_names = {t.__name__ for t in agent.tools if hasattr(t, "__name__")}
        assert EXPECTED_TOOLS[worker] <= tool_names

    def test_the_instruction_is_non_trivial(self, worker):
        agent = _module(worker).create_agent()
        instr = agent.instruction
        text = instr(None) if callable(instr) else instr
        assert len(text) > 200

    def test_a_worker_never_has_governance_tools(self, worker):
        """Only the orchestrator issues approvals; workers only get them checked."""
        agent = _module(worker).create_agent()
        names = {t.__name__ for t in agent.tools if hasattr(t, "__name__")}
        assert "request_approval" not in names
        assert "grant_approval" not in names


class TestCardsServe:
    def test_the_well_known_card_is_schema_valid(self, worker):
        module = _module(worker)
        app = build_server(
            module.create_agent(),
            skill=module.build_card_skill(),
            port=config.AGENT_PORTS[worker],
            description=module.DESCRIPTION,
        )
        with TestClient(app) as client:
            resp = client.get("/.well-known/agent-card.json")
        assert resp.status_code == 200
        card = resp.json()
        assert card["name"] == module.AGENT_NAME
        assert card["skills"], "a worker with no advertised skill cannot be routed to"
        assert card["skills"][0]["id"] == EXPECTED_SKILL[worker]
        assert card["skills"][0]["examples"], "examples help the orchestrator route"

    def test_the_card_advertises_streaming_and_push(self, worker):
        module = _module(worker)
        app = build_server(
            module.create_agent(),
            skill=module.build_card_skill(),
            port=config.AGENT_PORTS[worker],
            description=module.DESCRIPTION,
        )
        with TestClient(app) as client:
            card = client.get("/.well-known/agent-card.json").json()
        assert card["capabilities"]["streaming"] is True
        assert card["capabilities"].get("pushNotifications") is True

    def test_the_card_url_matches_the_configured_port(self, worker):
        module = _module(worker)
        port = config.AGENT_PORTS[worker]
        app = build_server(
            module.create_agent(), skill=module.build_card_skill(),
            port=port, description=module.DESCRIPTION,
        )
        with TestClient(app) as client:
            card = client.get("/.well-known/agent-card.json").json()
        url = card.get("url") or card["supportedInterfaces"][0]["url"]
        assert str(port) in url


class TestOrchestrator:
    def test_it_builds_with_delegation_and_lifecycle_tools(self, monkeypatch):
        monkeypatch.setattr(
            "augur_agents.config.ORCHESTRATOR_AUTOINIT", False
        )
        from augur_agents.orchestrator.agent import create_agent

        agent = create_agent()
        names = {t.__name__ for t in agent.tools}
        assert {"list_agents", "dispatch_task", "get_task"} <= names
        assert {"get_workflow", "advance_stage", "start_workflow"} <= names
        assert {"request_approval", "grant_approval"} <= names

    def test_it_has_no_sub_agents(self, monkeypatch):
        """The architecture: workers are tools, control never leaves here."""
        from augur_agents.orchestrator.agent import create_agent

        assert create_agent().sub_agents == []

    def test_it_carries_no_worker_tools_of_its_own(self):
        from augur_agents.orchestrator.agent import create_agent

        names = {t.__name__ for t in create_agent().tools}
        assert "submit_training_job" not in names
        assert "run_evaluation" not in names
        assert "inspect_dataset" not in names


def test_the_cli_lists_the_roster_without_touching_the_network(capsys):
    from augur_agents.__main__ import list_agents

    assert list_agents() == 0
    out = capsys.readouterr().out
    for worker in WORKERS:
        assert worker in out
    assert "orchestrator" in out

