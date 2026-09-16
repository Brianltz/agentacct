"""Read-back of user-scope MCP registrations, and the create-time warning
``init`` / ``onboard --scope project`` print before adding a project store on a
machine that already records globally. Read commands (tui / now / limits) stay
quiet and show the store the walk-up resolves.

HOME is redirected to a tmp dir so nothing here reads the real ~/.claude.json
or ~/.codex/config.toml.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agentacct.cli import app
from agentacct.registration_stores import project_store_create_warning, user_scope_registered_stores


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    return home


def _write_claude_registration(home: Path, store: Path, *, key: str = "agentacct") -> None:
    (home / ".claude.json").write_text(
        json.dumps(
            {
                "numStartups": 3,
                "mcpServers": {key: {"type": "stdio", "command": "/opt/agentacct", "args": ["mcp", "serve", "--store-dir", str(store)]}},
            }
        )
    )


def _write_codex_registration(home: Path, store: Path) -> None:
    (home / ".codex").mkdir(exist_ok=True)
    (home / ".codex" / "config.toml").write_text(
        "[mcp_servers.agentacct]\n"
        'command = "/opt/agentacct"\n'
        f'args = ["mcp", "serve", "--store-dir", {json.dumps(str(store))}]\n'
    )


def _global_store(home: Path) -> Path:
    store = home / ".local" / "state" / "agentacct" / "state"
    store.mkdir(parents=True)
    return store


# --- read-back -------------------------------------------------------------


def test_reads_claude_and_codex_user_registrations(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    store = _global_store(home)
    _write_claude_registration(home, store)
    _write_codex_registration(home, store)

    rows = user_scope_registered_stores(home=home)

    assert [(row.client, row.store_dir) for row in rows] == [("claude-code", store), ("codex", store)]
    assert rows[0].config_path == home / ".claude.json"
    assert rows[1].config_path == home / ".codex" / "config.toml"
    # A pre-rename registration key still counts.
    _write_claude_registration(home, store, key="agent-sentinel")
    assert [row.client for row in user_scope_registered_stores(home=home)] == ["claude-code", "codex"]


def test_missing_malformed_and_relative_registrations_contribute_nothing(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    # No files at all.
    assert user_scope_registered_stores(home=home) == []
    # Malformed JSON / TOML never raise.
    (home / ".claude.json").write_text("{not json")
    (home / ".codex").mkdir()
    (home / ".codex" / "config.toml").write_text("[mcp_servers.agentacct\n")
    assert user_scope_registered_stores(home=home) == []
    # A relative --store-dir in user scope depends on the client's cwd: unknown, not guessed.
    (home / ".claude.json").write_text(
        json.dumps({"mcpServers": {"agentacct": {"args": ["mcp", "serve", "--store-dir", ".agent-sentinel/state"]}}})
    )
    (home / ".codex" / "config.toml").write_text('[mcp_servers.agentacct]\nargs = ["mcp", "serve"]\n')
    assert user_scope_registered_stores(home=home) == []


# --- CLI wiring -------------------------------------------------------------


def _seed_project(root: Path) -> Path:
    root.mkdir()
    (root / ".git").mkdir()
    state = root / ".agent-sentinel" / "state"
    state.mkdir(parents=True)
    return state


def test_init_warns_before_creating_a_project_store_on_a_global_install(
    tmp_path: Path, isolated_home: Path
) -> None:
    store = _global_store(isolated_home)
    _write_claude_registration(isolated_home, store)
    project = tmp_path / "repo"
    project.mkdir()

    result = CliRunner().invoke(app, ["init", "--project-dir", str(project)])

    assert result.exit_code == 0, result.output
    assert (project / ".agent-sentinel" / "state").is_dir()
    # rich folds long paths at the console width; compare with newlines removed.
    unwrapped = result.output.replace("\n", "")
    assert "already records to" in unwrapped and str(store) in unwrapped

    # Second run: the store exists already, so there is nothing new to warn about.
    again = CliRunner().invoke(app, ["init", "--project-dir", str(project)])
    assert again.exit_code == 0, again.output
    assert "already records to" not in again.output


# --- create-time warning ----------------------------------------------------


def test_create_warning_names_the_recording_store(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    store = _global_store(home)
    _write_claude_registration(home, store)
    project_store = tmp_path / "repo" / ".agent-sentinel" / "state"

    lines = project_store_create_warning(project_store, home=home)

    assert lines and "already records to" in lines[0] and str(store) in lines[0]
    # Registered against the very store about to be created, or nothing registered: silent.
    assert project_store_create_warning(store, home=home) == []
    assert project_store_create_warning(project_store, home=tmp_path / "empty") == []


def test_now_reads_the_walked_up_project_store_quietly(
    tmp_path: Path, isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Read commands show the store the walk-up resolves and say nothing about
    where sessions record: that is a create-time concern (init / onboard)."""

    store = _global_store(isolated_home)
    _write_claude_registration(isolated_home, store)
    project = tmp_path / "repo"
    _seed_project(project)
    monkeypatch.delenv("AGENTACCT_STORE_DIR", raising=False)
    monkeypatch.delenv("AGENT_CHRONICLE_STORE_DIR", raising=False)
    monkeypatch.chdir(project)

    result = CliRunner().invoke(app, ["now", "--json"])

    assert result.exit_code == 0, result.output
    json.loads(result.stdout)
    assert "record" not in result.stderr
