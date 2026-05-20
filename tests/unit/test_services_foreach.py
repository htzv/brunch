from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from brunch.errors import WorkspaceNotFoundError
from brunch.models import ToolConfig, WorkspaceLocation
from brunch.services.foreach import foreach_workspace


def _write_manifest(ws: Path, *, repos: list[tuple[str, str, str]]) -> WorkspaceLocation:
    text = f'name = "{ws.name}"\n'
    for repo, branch, base in repos:
        text += f'\n[[repo]]\nrepo = "{repo}"\nbranch = "{branch}"\nbase = "{base}"\n'
    manifest_path = ws / "brunch.toml"
    manifest_path.write_text(text, encoding="utf-8")
    return WorkspaceLocation(mode="workspace", root=ws, manifest_path=manifest_path)


def _install_canonical(
    make_canonical: Callable[..., Path], canonical_root: Path, *, name: str
) -> Path:
    target = canonical_root / "github.com" / "acme" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(make_canonical(name)), str(target))
    return target


def _config(root: Path) -> ToolConfig:
    return ToolConfig(root=root, default_forge="github.com")


class TestForeachHappyPath:
    def test_runs_command_in_each_repo(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        a = _install_canonical(make_canonical, canonical_root, name="api")
        b = _install_canonical(make_canonical, canonical_root, name="dashboard")
        ws = make_workspace()
        worktree_factory(a, ws / "api", branch="feat", base="main")
        worktree_factory(b, ws / "dashboard", branch="feat", base="main")
        loc = _write_manifest(
            ws,
            repos=[
                ("acme/api", "feat", "main"),
                ("acme/dashboard", "feat", "main"),
            ],
        )
        report = foreach_workspace(
            loc, _config(canonical_root), command=["true"], capture_output=True
        )
        assert all(a.action == "ok" for a in report.actions)
        assert all(a.exit_code == 0 for a in report.actions)
        assert not report.has_errors

    def test_captures_stdout_when_requested(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        a = _install_canonical(make_canonical, canonical_root, name="api")
        ws = make_workspace()
        worktree_factory(a, ws / "api", branch="feat", base="main")
        loc = _write_manifest(ws, repos=[("acme/api", "feat", "main")])

        report = foreach_workspace(
            loc,
            _config(canonical_root),
            command=["sh", "-c", "echo hello"],
            capture_output=True,
        )
        assert report.actions[0].stdout is not None
        assert "hello" in report.actions[0].stdout

    def test_dry_run_runs_nothing(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        a = _install_canonical(make_canonical, canonical_root, name="api")
        ws = make_workspace()
        worktree_factory(a, ws / "api", branch="feat", base="main")
        loc = _write_manifest(ws, repos=[("acme/api", "feat", "main")])
        report = foreach_workspace(
            loc, _config(canonical_root), command=["false"], capture_output=True, dry_run=True
        )
        assert report.actions[0].action == "would_run"


class TestForeachFailures:
    def test_failure_stops_remaining_by_default(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        a = _install_canonical(make_canonical, canonical_root, name="api")
        b = _install_canonical(make_canonical, canonical_root, name="dashboard")
        ws = make_workspace()
        worktree_factory(a, ws / "api", branch="feat", base="main")
        worktree_factory(b, ws / "dashboard", branch="feat", base="main")
        loc = _write_manifest(
            ws,
            repos=[
                ("acme/api", "feat", "main"),
                ("acme/dashboard", "feat", "main"),
            ],
        )
        report = foreach_workspace(
            loc, _config(canonical_root), command=["false"], capture_output=True
        )
        assert report.actions[0].action == "failed"
        assert report.actions[1].action == "skipped"

    def test_continue_on_error_runs_all(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        a = _install_canonical(make_canonical, canonical_root, name="api")
        b = _install_canonical(make_canonical, canonical_root, name="dashboard")
        ws = make_workspace()
        worktree_factory(a, ws / "api", branch="feat", base="main")
        worktree_factory(b, ws / "dashboard", branch="feat", base="main")
        loc = _write_manifest(
            ws,
            repos=[
                ("acme/api", "feat", "main"),
                ("acme/dashboard", "feat", "main"),
            ],
        )
        report = foreach_workspace(
            loc,
            _config(canonical_root),
            command=["false"],
            capture_output=True,
            continue_on_error=True,
        )
        assert all(a.action == "failed" for a in report.actions)

    def test_unknown_command(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        a = _install_canonical(make_canonical, canonical_root, name="api")
        ws = make_workspace()
        worktree_factory(a, ws / "api", branch="feat", base="main")
        loc = _write_manifest(ws, repos=[("acme/api", "feat", "main")])
        report = foreach_workspace(
            loc,
            _config(canonical_root),
            command=["this-binary-does-not-exist-xyzzy"],
            capture_output=True,
        )
        assert report.actions[0].action == "error"


class TestForeachGuards:
    def test_skips_when_worktree_missing(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        _install_canonical(make_canonical, canonical_root, name="api")
        ws = make_workspace()
        loc = _write_manifest(ws, repos=[("acme/api", "feat", "main")])
        report = foreach_workspace(
            loc, _config(canonical_root), command=["true"], capture_output=True
        )
        assert report.actions[0].action == "skipped"

    def test_set_mode_rejected(self, tmp_path: Path) -> None:
        marker = tmp_path / "brunch-set.toml"
        marker.write_text('name = "s"\n', encoding="utf-8")
        loc = WorkspaceLocation(mode="set", root=tmp_path, manifest_path=marker)
        with pytest.raises(WorkspaceNotFoundError):
            foreach_workspace(loc, ToolConfig(), command=["true"])

    def test_empty_command_rejected(self, tmp_path: Path) -> None:
        marker = tmp_path / "brunch.toml"
        marker.write_text('name = "x"\n', encoding="utf-8")
        loc = WorkspaceLocation(mode="workspace", root=tmp_path, manifest_path=marker)
        with pytest.raises(WorkspaceNotFoundError):
            foreach_workspace(loc, ToolConfig(), command=[])
