"""CLI-level tests for `br agent` subcommands.

Cover the controller layer (``brunch.commands.agent``) and, through it, the
renderers — the service internals are exercised in ``test_services_agent.py``.
Providers are faked; ``subprocess.run`` / ``os.execvp`` are patched so nothing
actually launches.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from brunch import experimental
from brunch.cli import app
from brunch.manifest import load_workspace_manifest
from brunch.models import DiscoveredSession
from brunch.paths import discover_workspace
from brunch.services import agent as svc

runner = CliRunner()


class _FakeProvider:
    def __init__(self, kind, discovered=(), ids=(), assigned=False, available=True):
        self.kind = kind
        self.cli = kind
        self.supports_assigned_id = assigned
        self._discovered = list(discovered)
        self._ids = set(ids)
        self._available = available
        self.deleted: list[tuple[str, Path]] = []

    def available(self):
        return self._available

    def discover_under(self, root):
        return list(self._discovered)

    def session_ids_in(self, directory):
        return set(self._ids)

    def launch_argv(self, *, session_id):
        return [self.cli] + (["--session-id", session_id] if session_id else [])

    def resume_argv(self, session):
        return [self.cli, "--session", session]

    def delete_session(self, session_id, directory):
        self.deleted.append((session_id, directory))
        return True


def _disc(session, ws, *, active=False, title=None):
    when = datetime.now(UTC) if active else datetime.now(UTC) - timedelta(days=1)
    return DiscoveredSession(
        agent="opencode", session=session, dir=ws, title=title, last_active=when.isoformat()
    )


def _use(monkeypatch, fake):
    monkeypatch.setattr(svc, "all_providers", lambda: [fake])
    monkeypatch.setattr(svc, "get_provider", lambda kind: fake)


@pytest.fixture(autouse=True)
def _reset_experimental(monkeypatch):
    monkeypatch.delenv(experimental.ENV_VAR, raising=False)
    experimental.set_enabled(None)
    yield
    experimental.set_enabled(None)


# --- list ------------------------------------------------------------------


def test_list_table_and_json(make_workspace, monkeypatch):
    ws = make_workspace()
    _use(monkeypatch, _FakeProvider("opencode", discovered=[_disc("ses_a", ws, title="Work")]))
    r1 = runner.invoke(app, ["agent", "list", "-w", str(ws)])
    assert r1.exit_code == 0, r1.output
    r2 = runner.invoke(app, ["agent", "list", "-w", str(ws), "--json"])
    assert r2.exit_code == 0, r2.output
    assert '"conversations"' in r2.output


# --- register --------------------------------------------------------------


def test_register_records_entry(make_workspace, monkeypatch):
    ws = make_workspace()
    _use(monkeypatch, _FakeProvider("opencode"))
    r = runner.invoke(app, ["agent", "register", "opencode", "ses_x", "-w", str(ws), "-l", "ui"])
    assert r.exit_code == 0, r.output
    agents = load_workspace_manifest(ws / "brunch.toml").agents
    assert [a.session for a in agents] == ["ses_x"]


def test_register_unknown_kind_errors(make_workspace):
    ws = make_workspace()
    r = runner.invoke(app, ["agent", "register", "bogus", "ses_x", "-w", str(ws)])
    assert r.exit_code != 0
    assert "unknown agent" in r.output


# --- sync ------------------------------------------------------------------


def test_sync_adopts_and_json(make_workspace, monkeypatch):
    ws = make_workspace()
    _use(monkeypatch, _FakeProvider("opencode", discovered=[_disc("ses_new", ws, title="N")]))
    r = runner.invoke(app, ["agent", "sync", "-w", str(ws)])
    assert r.exit_code == 0, r.output
    r2 = runner.invoke(app, ["agent", "sync", "-w", str(ws), "--json"])
    assert r2.exit_code == 0, r2.output
    assert '"actions"' in r2.output


# --- resume ----------------------------------------------------------------


def test_resume_execs_agent(make_workspace, monkeypatch):
    ws = make_workspace()
    svc.register(discover_workspace(ws), "opencode", "ses_a", handle="h1", directory=ws)
    _use(monkeypatch, _FakeProvider("opencode", discovered=[_disc("ses_a", ws)]))
    called = {}
    monkeypatch.setattr(os, "chdir", lambda p: called.setdefault("chdir", p))
    monkeypatch.setattr(os, "execvp", lambda file, argv: called.setdefault("exec", (file, argv)))
    r = runner.invoke(app, ["agent", "resume", "-w", str(ws)])
    assert r.exit_code == 0, r.output
    assert called["exec"][0] == "opencode"


def test_resume_no_conversations_errors(make_workspace, monkeypatch):
    ws = make_workspace()
    _use(monkeypatch, _FakeProvider("opencode", discovered=[]))
    r = runner.invoke(app, ["agent", "resume", "-w", str(ws)])
    assert r.exit_code != 0
    assert "no agent conversations" in r.output


def test_resume_by_selector(make_workspace, monkeypatch):
    ws = make_workspace()
    svc.register(discover_workspace(ws), "opencode", "ses_a", handle="h1", directory=ws)
    svc.register(discover_workspace(ws), "opencode", "ses_b", handle="h2", directory=ws)
    _use(
        monkeypatch, _FakeProvider("opencode", discovered=[_disc("ses_a", ws), _disc("ses_b", ws)])
    )
    called = {}
    monkeypatch.setattr(os, "chdir", lambda p: None)
    monkeypatch.setattr(os, "execvp", lambda file, argv: called.setdefault("exec", (file, argv)))
    r = runner.invoke(app, ["agent", "resume", "h2", "-w", str(ws)])
    assert r.exit_code == 0, r.output
    assert called["exec"][1][-1] == "ses_b"


def test_resume_bad_selector_errors(make_workspace, monkeypatch):
    ws = make_workspace()
    svc.register(discover_workspace(ws), "opencode", "ses_a", handle="h1", directory=ws)
    _use(monkeypatch, _FakeProvider("opencode", discovered=[_disc("ses_a", ws)]))
    r = runner.invoke(app, ["agent", "resume", "zzz", "-w", str(ws)])
    assert r.exit_code != 0
    assert "no conversation matches" in r.output


def test_resume_picker_multiple(make_workspace, monkeypatch):
    # The interactive numbered picker needs a real tty, which CliRunner cannot
    # fake, so drive the controller directly with a stubbed stdin + prompt.
    from types import SimpleNamespace

    from brunch.commands.agent import agent_resume

    ws = make_workspace()
    svc.register(discover_workspace(ws), "opencode", "ses_a", handle="h1", directory=ws)
    svc.register(discover_workspace(ws), "opencode", "ses_b", handle="h2", directory=ws)
    _use(
        monkeypatch, _FakeProvider("opencode", discovered=[_disc("ses_a", ws), _disc("ses_b", ws)])
    )
    called = {}
    monkeypatch.setattr("brunch.commands.agent.sys.stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr("brunch.commands.agent.typer.prompt", lambda *a, **k: 1)
    monkeypatch.setattr(os, "chdir", lambda p: None)
    monkeypatch.setattr(os, "execvp", lambda file, argv: called.setdefault("exec", (file, argv)))
    agent_resume(selector=None, workspace=ws)
    assert "exec" in called


# --- new -------------------------------------------------------------------


def test_new_claude_records_and_launches(make_workspace, monkeypatch):
    ws = make_workspace()
    monkeypatch.setattr(svc, "get_provider", lambda kind: _FakeProvider("claude", assigned=True))
    launched = {}
    monkeypatch.setattr(
        "brunch.commands.agent.subprocess.run",
        lambda argv, **kw: launched.setdefault("argv", argv),
    )
    r = runner.invoke(app, ["agent", "new", "claude", "-w", str(ws), "-l", "x"])
    assert r.exit_code == 0, r.output
    assert launched["argv"][0] == "claude"
    assert len(load_workspace_manifest(ws / "brunch.toml").agents) == 1


def test_new_opencode_defers_capture(make_workspace, monkeypatch):
    ws = make_workspace()
    monkeypatch.setattr(svc, "get_provider", lambda kind: _FakeProvider("opencode", assigned=False))
    monkeypatch.setattr("brunch.commands.agent._capture_in_background", lambda loc, plan: None)
    monkeypatch.setattr("brunch.commands.agent.subprocess.run", lambda argv, **kw: None)
    r = runner.invoke(app, ["agent", "new", "opencode", "-w", str(ws)])
    assert r.exit_code == 0, r.output


def test_new_unknown_kind_errors(make_workspace):
    ws = make_workspace()
    r = runner.invoke(app, ["agent", "new", "bogus", "-w", str(ws)])
    assert r.exit_code != 0
    assert "unknown agent" in r.output


# --- rm (experimental) -----------------------------------------------------


def _register(ws, session="s1", handle="h1"):
    svc.register(discover_workspace(ws), "opencode", session, handle=handle, directory=ws)


def test_rm_unregister_with_optin(make_workspace, monkeypatch):
    ws = make_workspace()
    _register(ws)
    _use(monkeypatch, _FakeProvider("opencode", discovered=[_disc("s1", ws)]))
    r = runner.invoke(app, ["--enable-experimental=agent-rm", "agent", "rm", "h1", "-w", str(ws)])
    assert r.exit_code == 0, r.output
    assert load_workspace_manifest(ws / "brunch.toml").agents == []


def test_rm_purge_confirmed(make_workspace, monkeypatch):
    ws = make_workspace()
    _register(ws)
    fake = _FakeProvider("opencode", discovered=[_disc("s1", ws)])
    _use(monkeypatch, fake)
    r = runner.invoke(
        app,
        ["--enable-experimental=agent-rm", "agent", "rm", "h1", "--purge", "-w", str(ws)],
        input="y\n",
    )
    assert r.exit_code == 0, r.output
    assert [c[0] for c in fake.deleted] == ["s1"]


def test_rm_purge_declined_aborts(make_workspace, monkeypatch):
    ws = make_workspace()
    _register(ws)
    fake = _FakeProvider("opencode", discovered=[_disc("s1", ws)])
    _use(monkeypatch, fake)
    r = runner.invoke(
        app,
        ["--enable-experimental=agent-rm", "agent", "rm", "h1", "--purge", "-w", str(ws)],
        input="n\n",
    )
    assert r.exit_code != 0  # aborted
    assert fake.deleted == []  # nothing deleted


def test_rm_dry_run_with_optin(make_workspace, monkeypatch):
    ws = make_workspace()
    _register(ws)
    fake = _FakeProvider("opencode", discovered=[_disc("s1", ws)])
    _use(monkeypatch, fake)
    r = runner.invoke(
        app,
        [
            "--enable-experimental=agent-rm",
            "agent",
            "rm",
            "h1",
            "--purge",
            "--dry-run",
            "-w",
            str(ws),
        ],
    )
    assert r.exit_code == 0, r.output
    assert fake.deleted == []
    assert len(load_workspace_manifest(ws / "brunch.toml").agents) == 1


def test_rm_blocked_without_optin(make_workspace):
    ws = make_workspace()
    r = runner.invoke(app, ["agent", "rm", "h1", "-w", str(ws)])
    assert r.exit_code == 2  # experimental gate


# --- top-level --enable-experimental error path (cli.py) -------------------


def test_unknown_experimental_feature_errors(make_workspace):
    ws = make_workspace()
    r = runner.invoke(app, ["--enable-experimental=bogus", "agent", "list", "-w", str(ws)])
    assert r.exit_code != 0
    assert "unknown experimental" in r.output
