"""The agent roster - how the orchestrator learns who it can talk to."""

from __future__ import annotations

import pytest

from augur_agents import config, registry


@pytest.fixture
def roster_env(monkeypatch):
    """Reset roster config to the built-in defaults, then let a test override."""
    monkeypatch.setattr(config, "MOBIUS_AGENT_REGISTRY", "")
    monkeypatch.setattr(config, "MOBIUS_AGENT_REGISTRY_FILE", "")
    return monkeypatch


def test_default_roster_is_the_built_in_workers(roster_env):
    names = [ep.name for ep in registry.load_roster()]
    assert names == list(config.WORKER_NAMES)


def test_default_roster_points_at_the_configured_ports(roster_env):
    by_name = {ep.name: ep for ep in registry.load_roster()}
    assert by_name["data"].url.endswith(str(config.AGENT_PORTS["data"]))


class TestInlineRegistry:
    def test_parses_name_equals_url_pairs(self, roster_env):
        roster_env.setattr(
            config, "MOBIUS_AGENT_REGISTRY",
            "data=http://host-a:1,training=http://host-b:2",
        )
        roster = {ep.name: ep.url for ep in registry.load_roster()}
        assert roster == {
            "data": "http://host-a:1", "training": "http://host-b:2"
        }

    def test_a_trailing_slash_is_stripped_so_card_url_is_well_formed(self, roster_env):
        roster_env.setattr(
            config, "MOBIUS_AGENT_REGISTRY", "data=http://host:1/"
        )
        ep = registry.load_roster()[0]
        assert ep.card_url == "http://host:1/.well-known/agent-card.json"

    def test_a_malformed_entry_is_skipped_not_fatal(self, roster_env):
        """One bad line must not make the other agents unreachable."""
        roster_env.setattr(
            config, "MOBIUS_AGENT_REGISTRY",
            "data=http://host:1,garbage-no-equals,training=http://host:2",
        )
        names = [ep.name for ep in registry.load_roster()]
        assert names == ["data", "training"]

    def test_blank_entries_are_ignored(self, roster_env):
        roster_env.setattr(
            config, "MOBIUS_AGENT_REGISTRY", "data=http://host:1,, ,"
        )
        assert [ep.name for ep in registry.load_roster()] == ["data"]

    def test_a_duplicate_name_keeps_the_first(self, roster_env):
        roster_env.setattr(
            config, "MOBIUS_AGENT_REGISTRY",
            "data=http://first:1,data=http://second:2",
        )
        roster = registry.load_roster()
        assert len(roster) == 1
        assert roster[0].url == "http://first:1"


class TestTomlRegistry:
    def test_reads_the_agents_table_shape(self, roster_env, tmp_path):
        f = tmp_path / "agents.toml"
        f.write_text(
            '[agents]\n'
            'data = "http://host:10201"\n'
            'training = "http://host:10202"\n'
        )
        roster_env.setattr(config, "MOBIUS_AGENT_REGISTRY_FILE", str(f))
        roster = {ep.name: ep.url for ep in registry.load_roster()}
        assert roster["data"] == "http://host:10201"

    def test_reads_the_array_of_tables_shape(self, roster_env, tmp_path):
        f = tmp_path / "agents.toml"
        f.write_text(
            '[[agent]]\nname = "data"\nurl = "http://host:1"\n'
            '[[agent]]\nname = "training"\nurl = "http://host:2"\n'
        )
        roster_env.setattr(config, "MOBIUS_AGENT_REGISTRY_FILE", str(f))
        assert [ep.name for ep in registry.load_roster()] == ["data", "training"]

    def test_a_missing_file_yields_an_empty_roster_not_a_crash(self, roster_env):
        roster_env.setattr(
            config, "MOBIUS_AGENT_REGISTRY_FILE", "/no/such/agents.toml"
        )
        assert registry.load_roster() == []

    def test_malformed_toml_does_not_raise(self, roster_env, tmp_path):
        f = tmp_path / "agents.toml"
        f.write_text("this is [ not valid toml")
        roster_env.setattr(config, "MOBIUS_AGENT_REGISTRY_FILE", str(f))
        assert registry.load_roster() == []

    def test_a_non_string_url_is_skipped(self, roster_env, tmp_path):
        f = tmp_path / "agents.toml"
        f.write_text('[agents]\ndata = 12345\ntraining = "http://host:2"\n')
        roster_env.setattr(config, "MOBIUS_AGENT_REGISTRY_FILE", str(f))
        assert [ep.name for ep in registry.load_roster()] == ["training"]


def test_inline_registry_wins_over_a_file(roster_env, tmp_path):
    f = tmp_path / "agents.toml"
    f.write_text('[agents]\ndata = "http://from-file:1"\n')
    roster_env.setattr(config, "MOBIUS_AGENT_REGISTRY_FILE", str(f))
    roster_env.setattr(config, "MOBIUS_AGENT_REGISTRY", "data=http://from-env:2")
    assert registry.load_roster()[0].url == "http://from-env:2"

