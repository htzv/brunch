from __future__ import annotations

from io import StringIO
from pathlib import Path

from rich.console import Console

from brunch.models import FsckFinding, FsckReport, RepoStatus, WorkspaceStatus
from brunch.rendering import render_fsck_report, render_workspace_status


def _capture(fn, *args, **kwargs) -> str:
    buf = StringIO()
    console = Console(file=buf, width=140, force_terminal=False, color_system=None)
    fn(*args, console=console, **kwargs)
    return buf.getvalue()


def _repo_status(**overrides) -> RepoStatus:
    defaults = dict(
        repo_spec="acme/api",
        short_name="api",
        worktree_path=Path("/tmp/ws/api"),
        exists=True,
        current_branch="feat",
        declared_branch="feat",
        declared_base="main",
        on_declared_branch=True,
        ahead=0,
        behind=0,
        has_uncommitted=False,
        has_untracked=False,
    )
    defaults.update(overrides)
    return RepoStatus(**defaults)


class TestRenderWorkspaceStatus:
    def test_renders_empty_workspace(self) -> None:
        s = WorkspaceStatus(
            workspace_name="ws",
            workspace_path=Path("/tmp/ws"),
            description=None,
            repos=[],
        )
        out = _capture(render_workspace_status, s)
        assert "workspace" in out
        assert "no repos" in out

    def test_renders_description(self) -> None:
        s = WorkspaceStatus(
            workspace_name="ws",
            workspace_path=Path("/tmp/ws"),
            description="a description",
            repos=[],
        )
        out = _capture(render_workspace_status, s)
        assert "a description" in out

    def test_clean_repo_row(self) -> None:
        s = WorkspaceStatus(
            workspace_name="ws", workspace_path=Path("/tmp/ws"), repos=[_repo_status()]
        )
        out = _capture(render_workspace_status, s)
        assert "clean" in out

    def test_missing_repo_row(self) -> None:
        s = WorkspaceStatus(
            workspace_name="ws",
            workspace_path=Path("/tmp/ws"),
            repos=[
                _repo_status(
                    exists=False,
                    current_branch=None,
                    on_declared_branch=False,
                )
            ],
        )
        out = _capture(render_workspace_status, s)
        assert "missing" in out

    def test_dirty_repo_row(self) -> None:
        s = WorkspaceStatus(
            workspace_name="ws",
            workspace_path=Path("/tmp/ws"),
            repos=[_repo_status(has_uncommitted=True, has_untracked=True)],
        )
        out = _capture(render_workspace_status, s)
        assert "uncommitted" in out
        assert "untracked" in out

    def test_drift_repo_row(self) -> None:
        s = WorkspaceStatus(
            workspace_name="ws",
            workspace_path=Path("/tmp/ws"),
            repos=[
                _repo_status(
                    current_branch="actual",
                    declared_branch="declared",
                    on_declared_branch=False,
                )
            ],
        )
        out = _capture(render_workspace_status, s)
        assert "actual" in out
        assert "declared" in out

    def test_detached_repo_row(self) -> None:
        s = WorkspaceStatus(
            workspace_name="ws",
            workspace_path=Path("/tmp/ws"),
            repos=[_repo_status(current_branch=None, on_declared_branch=False)],
        )
        out = _capture(render_workspace_status, s)
        assert "detached" in out

    def test_ahead_behind_shown(self) -> None:
        s = WorkspaceStatus(
            workspace_name="ws",
            workspace_path=Path("/tmp/ws"),
            repos=[_repo_status(ahead=2, behind=3)],
        )
        out = _capture(render_workspace_status, s)
        assert "+2" in out
        assert "-3" in out


class TestRenderFsckReport:
    def test_empty_report_says_all_passed(self) -> None:
        r = FsckReport(workspace_name="ws", workspace_path=Path("/tmp/ws"), findings=[])
        out = _capture(render_fsck_report, r)
        assert "all checks passed" in out

    def test_renders_each_finding(self) -> None:
        r = FsckReport(
            workspace_name="ws",
            workspace_path=Path("/tmp/ws"),
            findings=[
                FsckFinding(
                    severity="error",
                    code="canonical-missing",
                    message="not found at /x",
                    repo="acme/api",
                    hint="clone it",
                ),
                FsckFinding(
                    severity="warning",
                    code="branch-drift",
                    message="declared vs actual",
                    repo="acme/api",
                ),
                FsckFinding(severity="info", code="something", message="fine to know"),
            ],
        )
        out = _capture(render_fsck_report, r)
        assert "1 error" in out
        assert "1 warning" in out
        assert "canonical-missing" in out
        assert "branch-drift" in out
        assert "clone it" in out

    def test_pluralisation(self) -> None:
        findings = [
            FsckFinding(severity="error", code="x", message="m"),
            FsckFinding(severity="error", code="y", message="m"),
        ]
        r = FsckReport(
            workspace_name="ws",
            workspace_path=Path("/tmp/ws"),
            findings=findings,
        )
        out = _capture(render_fsck_report, r)
        assert "2 errors" in out
