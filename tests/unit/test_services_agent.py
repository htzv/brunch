"""Tests for the `br agent` conversation registry: manifest round-trip,
the Claude/OpenCode provider adapters (against real fixture stores), and the
discovery-first merge/register/resume/sync service logic.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path

import pytest
import typer
from rich.console import Console
from typer.testing import CliRunner

from brunch import experimental
from brunch.agents import ClaudeProvider, OpenCodeProvider, _claude_slug
from brunch.cli import app
from brunch.errors import AgentError, BrunchError
from brunch.manifest import load_workspace_manifest, write_workspace_manifest
from brunch.models import (
    AgentConversation,
    AgentEntry,
    AgentList,
    AgentSyncAction,
    AgentSyncReport,
    DiscoveredSession,
    WorkspaceLocation,
    WorkspaceManifest,
)
from brunch.paths import discover_workspace
from brunch.rendering import render_agent_list, render_agent_sync
from brunch.services import agent as svc

# --- fixtures / helpers ----------------------------------------------------


def _location(ws: Path) -> WorkspaceLocation:
    return discover_workspace(ws)


def _write_claude_session(
    projects: Path, cwd: Path, session_id: str, *, title: str | None = None
) -> Path:
    """Write a minimal Claude session jsonl the way the real store lays it out."""

    proj = projects / _claude_slug(cwd)
    proj.mkdir(parents=True, exist_ok=True)
    f = proj / f"{session_id}.jsonl"
    lines = [
        {"type": "summary", "sessionId": session_id, "mode": "default"},  # line 1 has no cwd
        {"type": "user", "sessionId": session_id, "cwd": str(cwd)},
    ]
    if title is not None:
        lines.append({"type": "ai-title", "aiTitle": title})
    f.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    return f


def _make_opencode_db(path: Path, rows: list[dict]) -> None:
    """Create a fixture opencode.db with the columns the provider queries."""

    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE session ("
        "id TEXT PRIMARY KEY, parent_id TEXT, directory TEXT, title TEXT, "
        "time_updated INTEGER, time_archived INTEGER)"
    )
    conn.executemany(
        "INSERT INTO session (id, parent_id, directory, title, time_updated, time_archived) "
        "VALUES (:id, :parent_id, :directory, :title, :time_updated, :time_archived)",
        [
            {
                "parent_id": None,
                "title": None,
                "time_updated": 1_700_000_000_000,
                "time_archived": None,
                **r,
            }
            for r in rows
        ],
    )
    conn.commit()
    conn.close()


# --- manifest round-trip ---------------------------------------------------


class TestManifestAgents:
    def test_round_trip_with_agents(self, tmp_path: Path) -> None:
        m = WorkspaceManifest(
            name="t",
            agent=[
                AgentEntry(handle="h1", agent="claude", session="h1", dir="."),
                AgentEntry(
                    handle="h2", agent="opencode", session="ses_x", dir="frontend", label="ui"
                ),
            ],
        )
        path = tmp_path / "brunch.toml"
        write_workspace_manifest(path, m)
        assert load_workspace_manifest(path) == m
        # brunch serializes tables as inline arrays (same style as [[repo]]).
        assert "agent = [" in path.read_text(encoding="utf-8")

    def test_no_agents_omits_section(self, tmp_path: Path) -> None:
        path = tmp_path / "brunch.toml"
        write_workspace_manifest(path, WorkspaceManifest(name="t"))
        assert "[[agent]]" not in path.read_text(encoding="utf-8")

    def test_unknown_agent_field_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "brunch.toml"
        path.write_text(
            'name = "t"\n[[agent]]\nhandle = "h"\nagent = "claude"\nsession = "s"\nmystery = "y"\n',
            encoding="utf-8",
        )
        from brunch.errors import ManifestError

        with pytest.raises(ManifestError):
            load_workspace_manifest(path)


# --- Claude provider -------------------------------------------------------


class TestClaudeProvider:
    def test_slug_matches_real_format(self) -> None:
        assert (
            _claude_slug(Path("/home/ar/repos/vida.place/tasks/2026-07_x"))
            == "-home-ar-repos-vida-place-tasks-2026-07-x"
        )

    def test_discover_root_and_subdir(self, tmp_path: Path) -> None:
        root = tmp_path / "task"
        (root / "frontend").mkdir(parents=True)
        projects = tmp_path / "claude" / "projects"
        _write_claude_session(projects, root, "11111111-1111-1111-1111-111111111111", title="Root")
        _write_claude_session(
            projects, root / "frontend", "22222222-2222-2222-2222-222222222222", title="FE"
        )
        found = ClaudeProvider(projects_dir=projects).discover_under(root)
        by_id = {d.session: d for d in found}
        assert set(by_id) == {
            "11111111-1111-1111-1111-111111111111",
            "22222222-2222-2222-2222-222222222222",
        }
        assert by_id["11111111-1111-1111-1111-111111111111"].title == "Root"
        assert by_id["22222222-2222-2222-2222-222222222222"].dir == (root / "frontend")

    def test_excludes_slug_prefix_false_positive(self, tmp_path: Path) -> None:
        # /task and /task-sibling share the "-…-task" prefix but are different roots.
        root = tmp_path / "task"
        sibling = tmp_path / "task-sibling"
        root.mkdir()
        sibling.mkdir()
        projects = tmp_path / "claude" / "projects"
        _write_claude_session(projects, sibling, "33333333-3333-3333-3333-333333333333")
        found = ClaudeProvider(projects_dir=projects).discover_under(root)
        assert found == []

    def test_session_ids_in_and_argv(self, tmp_path: Path) -> None:
        root = tmp_path / "task"
        root.mkdir()
        projects = tmp_path / "claude" / "projects"
        _write_claude_session(projects, root, "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        p = ClaudeProvider(projects_dir=projects)
        assert p.session_ids_in(root) == {"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}
        assert p.supports_assigned_id is True
        assert p.launch_argv(session_id="x") == ["claude", "--session-id", "x"]
        assert p.resume_argv("x") == ["claude", "--resume", "x"]

    def test_missing_store_is_empty(self, tmp_path: Path) -> None:
        assert ClaudeProvider(projects_dir=tmp_path / "nope").discover_under(tmp_path) == []


# --- OpenCode provider -----------------------------------------------------


class TestOpenCodeProvider:
    def test_discover_scopes_by_directory(self, tmp_path: Path) -> None:
        root = tmp_path / "task"
        (root / "frontend").mkdir(parents=True)
        other = tmp_path / "other"
        other.mkdir()
        db = tmp_path / "share" / "opencode" / "opencode.db"
        _make_opencode_db(
            db,
            [
                {"id": "ses_root", "directory": str(root), "title": "Root work"},
                {"id": "ses_fe", "directory": str(root / "frontend"), "title": "FE"},
                {"id": "ses_other", "directory": str(other)},  # different root → excluded
                {"id": "ses_sub", "parent_id": "ses_root", "directory": str(root)},  # subagent
                {"id": "ses_arch", "directory": str(root), "time_archived": 123},  # archived
            ],
        )
        found = OpenCodeProvider(db_path=db).discover_under(root)
        assert {d.session for d in found} == {"ses_root", "ses_fe"}
        assert next(d for d in found if d.session == "ses_root").title == "Root work"

    def test_session_ids_in_exact_dir(self, tmp_path: Path) -> None:
        root = tmp_path / "task"
        root.mkdir()
        db = tmp_path / "share" / "opencode" / "opencode.db"
        _make_opencode_db(
            db,
            [
                {"id": "ses_a", "directory": str(root)},
                {"id": "ses_fork", "directory": str(root)},  # fork: parent_id NULL, same dir
            ],
        )
        p = OpenCodeProvider(db_path=db)
        assert p.session_ids_in(root) == {"ses_a", "ses_fork"}
        assert p.supports_assigned_id is False
        assert p.launch_argv(session_id="ignored") == ["opencode"]
        assert p.resume_argv("ses_a") == ["opencode", "--session", "ses_a"]

    def test_missing_db_is_empty(self, tmp_path: Path) -> None:
        assert OpenCodeProvider(db_path=tmp_path / "nope.db").discover_under(tmp_path) == []


# --- service: merge / match / register -------------------------------------


class _FakeProvider:
    def __init__(self, kind, discovered=(), ids=(), assigned=False, available=True):
        self.kind = kind
        self.cli = kind
        self.supports_assigned_id = assigned
        self._discovered = list(discovered)
        self._ids = set(ids)
        self._available = available
        self.deleted: list[tuple[str, Path]] = []
        self.delete_result = True

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
        return self.delete_result


class TestListMerge:
    def test_registered_discovered_stale(self, make_workspace, tmp_path: Path) -> None:
        ws = make_workspace()
        loc = _location(ws)
        # one registered+present, one registered-but-missing (stale)
        svc.register(loc, "opencode", "ses_present", handle="present", directory=ws)
        svc.register(loc, "opencode", "ses_gone", handle="gone", directory=ws)
        fake = _FakeProvider(
            "opencode",
            discovered=[
                DiscoveredSession(agent="opencode", session="ses_present", dir=ws, title="P"),
                DiscoveredSession(agent="opencode", session="ses_new", dir=ws, title="N"),
            ],
        )
        listing = svc.list_conversations(loc, providers=[fake])
        by = {c.session: c for c in listing.conversations}
        assert by["ses_present"].state == "registered"
        assert by["ses_present"].title == "P"
        assert by["ses_gone"].state == "stale"
        assert by["ses_new"].state == "discovered"
        assert len(listing.unregistered) == 1
        assert len(listing.stale) == 1

    def test_register_is_idempotent_and_relativizes_dir(self, make_workspace) -> None:
        ws = make_workspace()
        (ws / "frontend").mkdir()
        loc = _location(ws)
        e1 = svc.register(loc, "opencode", "ses_x", directory=ws / "frontend", label="ui")
        assert e1.dir == "frontend"
        e2 = svc.register(loc, "opencode", "ses_x", directory=ws)  # same (agent,session)
        assert e1 == e2
        assert len(load_workspace_manifest(loc.manifest_path).agents) == 1

    def test_unregister(self, make_workspace) -> None:
        ws = make_workspace()
        loc = _location(ws)
        svc.register(loc, "claude", "s", directory=ws)
        assert svc.unregister(loc, "claude", "s") is True
        assert svc.unregister(loc, "claude", "s") is False


class TestMatch:
    def _convs(self):
        return [
            AgentConversation(
                handle="abcdef12",
                agent="claude",
                session="abcdef12",
                dir=".",
                label="Docs work",
                state="registered",
            ),
            AgentConversation(
                handle="99887766", agent="opencode", session="ses_zzz", dir=".", state="registered"
            ),
        ]

    def test_exact_and_label_and_prefix(self) -> None:
        cs = self._convs()
        assert svc.match_conversation(cs, "ses_zzz").session == "ses_zzz"
        assert svc.match_conversation(cs, "docs WORK").handle == "abcdef12"
        assert svc.match_conversation(cs, "abcd").handle == "abcdef12"
        assert svc.match_conversation(cs, "nope") is None


# --- service: plan_new / capture_new / sync --------------------------------


class TestNewAndCapture:
    def test_plan_new_claude_registers_up_front(self, make_workspace, monkeypatch) -> None:
        ws = make_workspace()
        loc = _location(ws)
        monkeypatch.setattr(
            svc, "get_provider", lambda kind: _FakeProvider("claude", assigned=True)
        )
        plan = svc.plan_new(loc, "claude", label="x")
        assert plan.session_id is not None
        assert plan.argv == ["claude", "--session-id", plan.session_id]
        # already recorded
        agents_now = load_workspace_manifest(loc.manifest_path).agents
        assert [a.session for a in agents_now] == [plan.session_id]
        assert svc.capture_new(loc, plan) == []  # no-op for claude

    def test_plan_new_opencode_defers_then_captures(self, make_workspace, monkeypatch) -> None:
        ws = make_workspace()
        loc = _location(ws)
        provider = _FakeProvider("opencode", assigned=False, ids=set())  # empty before launch
        monkeypatch.setattr(svc, "get_provider", lambda kind: provider)
        plan = svc.plan_new(loc, "opencode", label="ui")
        assert plan.session_id is None
        assert plan.pre_snapshot == set()
        assert load_workspace_manifest(loc.manifest_path).agents == []  # nothing yet
        # a session appears in the store → capture records it under the plan handle
        provider._ids = {"ses_new"}
        recorded = svc.capture_new(loc, plan)
        assert [e.session for e in recorded] == ["ses_new"]
        assert recorded[0].handle == plan.handle
        assert recorded[0].label == "ui"
        # idempotent
        assert svc.capture_new(loc, plan) == []

    def test_capture_forks_get_parent(self, make_workspace, monkeypatch) -> None:
        ws = make_workspace()
        loc = _location(ws)
        provider = _FakeProvider("opencode", ids=set())
        monkeypatch.setattr(svc, "get_provider", lambda kind: provider)
        plan = svc.plan_new(loc, "opencode")
        provider._ids = {"ses_1", "ses_2"}  # a fork appeared during the session
        recorded = svc.capture_new(loc, plan)
        assert len(recorded) == 2
        primary = [e for e in recorded if e.handle == plan.handle]
        forks = [e for e in recorded if e.parent == plan.handle]
        assert len(primary) == 1 and len(forks) == 1

    def test_plan_new_rejects_subdir_escape(self, make_workspace, monkeypatch) -> None:
        ws = make_workspace()
        loc = _location(ws)
        monkeypatch.setattr(
            svc, "get_provider", lambda kind: _FakeProvider("claude", assigned=True)
        )
        with pytest.raises(AgentError, match="outside the workspace"):
            svc.plan_new(loc, "claude", subdir="../evil")


class TestSync:
    def test_adopts_and_flags_and_prunes(self, make_workspace, monkeypatch) -> None:
        ws = make_workspace()
        loc = _location(ws)
        svc.register(loc, "opencode", "ses_gone", handle="gone", directory=ws)  # will be stale
        fake = _FakeProvider(
            "opencode",
            discovered=[DiscoveredSession(agent="opencode", session="ses_new", dir=ws, title="N")],
        )
        monkeypatch.setattr(svc, "all_providers", lambda: [fake])

        report = svc.sync(loc)
        assert len(report.adopted) == 1
        assert report.adopted[0].session == "ses_new"
        assert report.adopted[0].label == "N"
        assert len(report.stale) == 1

        # discovered got adopted → now in manifest; stale still present (not pruned)
        sessions = {a.session for a in load_workspace_manifest(loc.manifest_path).agents}
        assert sessions == {"ses_gone", "ses_new"}

        # prune drops the stale one
        report2 = svc.sync(loc, prune=True)
        assert any(a.action == "pruned" for a in report2.actions)
        sessions2 = {a.session for a in load_workspace_manifest(loc.manifest_path).agents}
        assert sessions2 == {"ses_new"}


# --- rendering: markup safety (regression) ---------------------------------


class TestRenderMarkupSafety:
    """Paths and store-supplied titles must never be parsed as Rich markup.

    Regression: a dir like ``/home/ar/x`` rendered as ``[/home/ar/x]`` reads as
    a stray closing tag and raised MarkupError on `br agent resume`.
    """

    def test_list_survives_paths_and_bracketed_labels(self) -> None:
        listing = AgentList(
            workspace_name="w",
            workspace_path=Path("/w"),
            conversations=[
                AgentConversation(
                    handle="h1",
                    agent="claude",
                    session="s1",
                    dir="/home/ar/repos/vida.place/tasks/x",  # leading slash → old crash
                    state="registered",
                    label="[bold]not a tag[/bold] and [/oops]",  # injection attempt
                    last_active="2026-08-20T20:42:00+00:00",
                ),
            ],
        )
        buf = StringIO()
        render_agent_list(listing, console=Console(file=buf, width=200))
        out = buf.getvalue()
        assert "not a tag" in out  # rendered literally, no exception
        assert "/home/ar/repos/vida.place/tasks/x" in out

    def test_sync_survives_paths_and_bracketed_labels(self) -> None:
        report = AgentSyncReport(
            workspace_name="w",
            workspace_path=Path("/w"),
            actions=[
                AgentSyncAction(
                    action="adopted",
                    agent="claude",
                    handle="h1",
                    session="s1",
                    dir="/p/q",
                    label="weird [/x] label",
                ),
                AgentSyncAction(
                    action="stale", agent="opencode", handle="h2", session="ses_z", dir="/a/b"
                ),
            ],
        )
        buf = StringIO()
        render_agent_sync(report, console=Console(file=buf, width=200))
        out = buf.getvalue()
        assert "/p/q" in out
        assert "weird" in out


# --- experimental gate -----------------------------------------------------


class TestExperimentalGate:
    @pytest.fixture(autouse=True)
    def _reset(self, monkeypatch):
        monkeypatch.delenv(experimental.ENV_VAR, raising=False)
        experimental.set_enabled(None)
        yield
        experimental.set_enabled(None)

    def test_enable_and_query(self):
        experimental.set_enabled("agent-rm")
        assert experimental.is_enabled("agent-rm")
        experimental.set_enabled(None)
        assert not experimental.is_enabled("agent-rm")

    def test_dedup_and_whitespace(self):
        experimental.set_enabled(" agent-rm , agent-rm ")
        assert experimental.is_enabled("agent-rm")

    def test_unknown_feature_rejected(self):
        with pytest.raises(BrunchError, match="unknown experimental"):
            experimental.set_enabled("bogus")

    def test_env_var(self, monkeypatch):
        monkeypatch.setenv(experimental.ENV_VAR, "agent-rm")
        experimental.set_enabled(None)
        assert experimental.is_enabled("agent-rm")

    def test_require_enabled_is_noop(self):
        experimental.set_enabled("agent-rm")
        experimental.require("agent-rm")  # must not raise

    def test_require_disabled_exits_loudly(self, capsys):
        with pytest.raises(typer.Exit) as exc:
            experimental.require("agent-rm")
        assert exc.value.exit_code == 2
        err = capsys.readouterr().err
        assert "EXPERIMENTAL" in err
        assert "agent-rm" in err
        assert "--enable-experimental" in err


# --- provider deletion -----------------------------------------------------


class TestProviderDelete:
    def test_claude_delete_removes_file_and_is_idempotent(self, tmp_path: Path) -> None:
        root = tmp_path / "task"
        root.mkdir()
        projects = tmp_path / "claude" / "projects"
        sid = "abcd1234-abcd-1234-abcd-1234abcd1234"
        f = _write_claude_session(projects, root, sid)
        p = ClaudeProvider(projects_dir=projects)
        assert f.exists()
        assert p.delete_session(sid, root) is True
        assert not f.exists()
        assert p.delete_session(sid, root) is False  # already gone

    def test_claude_delete_rejects_unsafe_id(self, tmp_path: Path) -> None:
        # Ids with a path separator, whitespace, or empty are rejected by the id
        # guard; pure-dot ids like ".." stay a filename component and are caught
        # by the path-safety check instead (covered separately).
        p = ClaudeProvider(projects_dir=tmp_path / "projects")
        for bad in ["../evil", "a/b", "x y", "", "a b/c"]:
            with pytest.raises(ValueError):
                p.delete_session(bad, tmp_path)

    def test_opencode_delete_shells_out(self, tmp_path: Path, monkeypatch) -> None:
        import subprocess as sp

        seen = {}

        def fake_run(argv, **kw):
            seen["argv"] = argv
            return sp.CompletedProcess(argv, 0, "", "")

        monkeypatch.setattr("brunch.agents.shutil.which", lambda c: "/usr/bin/" + c)
        monkeypatch.setattr("brunch.agents.subprocess.run", fake_run)
        p = OpenCodeProvider(db_path=tmp_path / "x.db")
        assert p.delete_session("ses_abc", tmp_path) is True
        assert seen["argv"] == ["opencode", "session", "delete", "ses_abc"]

    def test_opencode_delete_raises_on_failure(self, tmp_path: Path, monkeypatch) -> None:
        import subprocess as sp

        monkeypatch.setattr("brunch.agents.shutil.which", lambda c: "/usr/bin/" + c)
        monkeypatch.setattr(
            "brunch.agents.subprocess.run",
            lambda argv, **kw: sp.CompletedProcess(argv, 1, "", "boom"),
        )
        p = OpenCodeProvider(db_path=tmp_path / "x.db")
        with pytest.raises(RuntimeError, match="failed"):
            p.delete_session("ses_abc", tmp_path)

    def test_opencode_delete_requires_cli(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr("brunch.agents.shutil.which", lambda c: None)
        p = OpenCodeProvider(db_path=tmp_path / "x.db")
        with pytest.raises(RuntimeError, match="PATH"):
            p.delete_session("ses_abc", tmp_path)


# --- service: remove -------------------------------------------------------


def _disc(session: str, ws: Path, *, active: bool = False) -> DiscoveredSession:
    when = datetime.now(UTC) if active else datetime.now(UTC) - timedelta(days=1)
    return DiscoveredSession(
        agent="opencode", session=session, dir=ws, last_active=when.isoformat()
    )


class TestRemove:
    def _providers(self, monkeypatch, fake) -> None:
        monkeypatch.setattr(svc, "all_providers", lambda: [fake])
        monkeypatch.setattr(svc, "get_provider", lambda kind: fake)

    def test_unregister_registered(self, make_workspace, monkeypatch) -> None:
        ws = make_workspace()
        loc = _location(ws)
        svc.register(loc, "opencode", "s1", handle="h1", directory=ws)
        self._providers(monkeypatch, _FakeProvider("opencode", discovered=[_disc("s1", ws)]))
        out = svc.remove(loc, "h1")
        assert out.unregistered and not out.purged
        assert load_workspace_manifest(loc.manifest_path).agents == []

    def test_discovered_only_without_purge_errors(self, make_workspace, monkeypatch) -> None:
        ws = make_workspace()
        loc = _location(ws)
        self._providers(monkeypatch, _FakeProvider("opencode", discovered=[_disc("s2", ws)]))
        with pytest.raises(AgentError, match="not recorded"):
            svc.remove(loc, "s2")

    def test_absent_selector_errors(self, make_workspace, monkeypatch) -> None:
        ws = make_workspace()
        loc = _location(ws)
        self._providers(monkeypatch, _FakeProvider("opencode", discovered=[_disc("s1", ws)]))
        with pytest.raises(AgentError, match="no conversation matches"):
            svc.remove(loc, "zzz")

    def test_purge_registered_present(self, make_workspace, monkeypatch) -> None:
        ws = make_workspace()
        loc = _location(ws)
        svc.register(loc, "opencode", "s1", handle="h1", directory=ws)
        fake = _FakeProvider("opencode", discovered=[_disc("s1", ws)])
        self._providers(monkeypatch, fake)
        out = svc.remove(loc, "h1", purge=True)
        assert out.purged and out.unregistered and not out.store_missing
        assert [c[0] for c in fake.deleted] == ["s1"]
        assert load_workspace_manifest(loc.manifest_path).agents == []

    def test_purge_stale_skips_store(self, make_workspace, monkeypatch) -> None:
        ws = make_workspace()
        loc = _location(ws)
        svc.register(loc, "opencode", "s_gone", handle="h1", directory=ws)
        self._providers(monkeypatch, (fake := _FakeProvider("opencode", discovered=[])))
        out = svc.remove(loc, "h1", purge=True)
        assert out.store_missing and out.unregistered and not out.purged
        assert fake.deleted == []
        assert load_workspace_manifest(loc.manifest_path).agents == []

    def test_purge_discovered_only(self, make_workspace, monkeypatch) -> None:
        ws = make_workspace()
        loc = _location(ws)
        fake = _FakeProvider("opencode", discovered=[_disc("s2", ws)])
        self._providers(monkeypatch, fake)
        out = svc.remove(loc, "s2", purge=True)
        assert out.purged and not out.unregistered
        assert [c[0] for c in fake.deleted] == ["s2"]

    def test_purge_active_guard(self, make_workspace, monkeypatch) -> None:
        ws = make_workspace()
        loc = _location(ws)
        svc.register(loc, "opencode", "s1", handle="h1", directory=ws)
        fake = _FakeProvider("opencode", discovered=[_disc("s1", ws, active=True)])
        self._providers(monkeypatch, fake)
        with pytest.raises(AgentError, match="looks active"):
            svc.remove(loc, "h1", purge=True)
        assert fake.deleted == []
        # --force overrides the guard
        out = svc.remove(loc, "h1", purge=True, force=True)
        assert out.purged

    def test_purge_opencode_cli_unavailable(self, make_workspace, monkeypatch) -> None:
        ws = make_workspace()
        loc = _location(ws)
        svc.register(loc, "opencode", "s1", handle="h1", directory=ws)
        fake = _FakeProvider("opencode", discovered=[_disc("s1", ws)], available=False)
        self._providers(monkeypatch, fake)
        with pytest.raises(AgentError, match="not on PATH"):
            svc.remove(loc, "h1", purge=True)

    def test_dry_run_changes_nothing(self, make_workspace, monkeypatch) -> None:
        ws = make_workspace()
        loc = _location(ws)
        svc.register(loc, "opencode", "s1", handle="h1", directory=ws)
        fake = _FakeProvider("opencode", discovered=[_disc("s1", ws)])
        self._providers(monkeypatch, fake)
        out = svc.remove(loc, "h1", purge=True, dry_run=True)
        assert out.dry_run and not out.purged
        assert fake.deleted == []
        assert len(load_workspace_manifest(loc.manifest_path).agents) == 1


# --- CLI: experimental gate on `br agent rm` -------------------------------


class TestAgentRmCli:
    @pytest.fixture(autouse=True)
    def _reset(self, monkeypatch):
        monkeypatch.delenv(experimental.ENV_VAR, raising=False)
        experimental.set_enabled(None)
        yield
        experimental.set_enabled(None)

    def test_gate_blocks_without_optin(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(app, ["agent", "rm", "whatever"])
        assert result.exit_code == 2  # refused by the experimental gate

    def test_gate_opens_with_optin(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)  # no brunch.toml here
        result = CliRunner().invoke(
            app, ["--enable-experimental=agent-rm", "agent", "rm", "whatever"]
        )
        # Gate passed; the command then fails to find a workspace (exit 3), not 2.
        assert result.exit_code != 2
