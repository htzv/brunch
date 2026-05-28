from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from brunch.errors import WorkspaceNotFoundError
from brunch.models import ToolConfig, WorkspaceLocation
from brunch.services.sync import sync_workspace


def _workspace_with(ws: Path, *, repos: list[tuple[str, str, str]]) -> WorkspaceLocation:
    text = f'name = "{ws.name}"\n'
    for repo, branch, base in repos:
        text += f'\n[[repo]]\nrepo = "{repo}"\nbranch = "{branch}"\nbase = "{base}"\n'
    manifest_path = ws / "brunch.toml"
    manifest_path.write_text(text, encoding="utf-8")
    return WorkspaceLocation(mode="workspace", root=ws, manifest_path=manifest_path)


def _setup_canonical(
    make_canonical: Callable[..., Path], canonical_root: Path, *, name: str
) -> Path:
    target = canonical_root / "github.com" / "kybernetix" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(make_canonical(name)), str(target))
    return target


def _config(canonical_root: Path) -> ToolConfig:
    return ToolConfig(root=canonical_root, default_forge="github.com")


def _by_action(actions) -> dict[str, list]:
    out: dict[str, list] = {}
    for a in actions:
        out.setdefault(a.action, []).append(a)
    return out


class TestSyncCreatesMissingWorktrees:
    def test_creates_worktree_for_each_entry(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        _setup_canonical(make_canonical, canonical_root, name="api")
        _setup_canonical(make_canonical, canonical_root, name="dashboard")

        ws = make_workspace()
        loc = _workspace_with(
            ws,
            repos=[
                ("kybernetix/api", "feat", "main"),
                ("kybernetix/dashboard", "feat", "main"),
            ],
        )
        report = sync_workspace(loc, _config(canonical_root))
        assert report.dry_run is False
        by_action = _by_action(report.actions)
        assert "created" in by_action
        assert len(by_action["created"]) == 2
        assert (ws / "api").is_dir()
        assert (ws / "dashboard").is_dir()

    def test_dry_run_does_not_create(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        _setup_canonical(make_canonical, canonical_root, name="api")

        ws = make_workspace()
        loc = _workspace_with(ws, repos=[("kybernetix/api", "feat", "main")])
        report = sync_workspace(loc, _config(canonical_root), dry_run=True)
        assert report.dry_run is True
        action = report.actions[0]
        assert action.action == "created"
        assert action.message.startswith("would create")
        assert not (ws / "api").exists()


class TestSyncWarnings:
    def test_drift_is_a_warning(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        canonical = _setup_canonical(make_canonical, canonical_root, name="api")
        ws = make_workspace()
        worktree_factory(canonical, ws / "api", branch="actual", base="main")
        loc = _workspace_with(ws, repos=[("kybernetix/api", "declared", "main")])
        report = sync_workspace(loc, _config(canonical_root))
        assert report.has_warnings
        assert report.actions[0].action == "warning"
        assert "actual" in report.actions[0].message

    def test_dirty_worktree_is_a_warning(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        canonical = _setup_canonical(make_canonical, canonical_root, name="api")
        ws = make_workspace()
        worktree_factory(canonical, ws / "api", branch="feat", base="main")
        (ws / "api" / "README.md").write_text("dirty\n", encoding="utf-8")
        loc = _workspace_with(ws, repos=[("kybernetix/api", "feat", "main")])
        report = sync_workspace(loc, _config(canonical_root))
        assert report.actions[0].action == "warning"
        assert "uncommitted" in report.actions[0].message


class TestSyncErrors:
    def test_missing_canonical_is_an_error(
        self,
        tmp_path: Path,
        make_workspace: Callable[..., Path],
    ) -> None:
        ws = make_workspace()
        loc = _workspace_with(ws, repos=[("kybernetix/api", "f", "main")])
        report = sync_workspace(loc, _config(tmp_path / "no-root"))
        assert report.has_errors
        assert "canonical clone not found" in report.actions[0].message

    def test_branch_in_use_elsewhere_blocks_creation(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        canonical = _setup_canonical(make_canonical, canonical_root, name="api")
        # Park the branch we want in a separate worktree first.
        worktree_factory(canonical, tmp_path / "park", branch="contested", base="main")

        ws = make_workspace()
        loc = _workspace_with(ws, repos=[("kybernetix/api", "contested", "main")])
        report = sync_workspace(loc, _config(canonical_root))
        assert report.has_errors
        msg = report.actions[0].message
        assert "already checked out" in msg


class TestSyncIdempotence:
    def test_running_twice_yields_ok(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        _setup_canonical(make_canonical, canonical_root, name="api")
        ws = make_workspace()
        loc = _workspace_with(ws, repos=[("kybernetix/api", "feat", "main")])
        sync_workspace(loc, _config(canonical_root))
        second = sync_workspace(loc, _config(canonical_root))
        assert second.actions[0].action == "ok"


class TestSyncRejectsSetMode:
    def test_set_mode_rejected(self, tmp_path: Path) -> None:
        marker = tmp_path / "brunch-set.toml"
        marker.write_text('name = "s"\n', encoding="utf-8")
        loc = WorkspaceLocation(mode="set", root=tmp_path, manifest_path=marker)
        with pytest.raises(WorkspaceNotFoundError):
            sync_workspace(loc, ToolConfig())
