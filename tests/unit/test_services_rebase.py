from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from brunch.errors import WorkspaceNotFoundError
from brunch.models import ToolConfig, WorkspaceLocation
from brunch.services.rebase import rebase_workspace


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
    target = canonical_root / "github.com" / "kybernetix" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(make_canonical(name)), str(target))
    return target


def _config(root: Path) -> ToolConfig:
    return ToolConfig(root=root, default_forge="github.com")


def _commit(repo: Path, filename: str, content: str, message: str) -> None:
    (repo / filename).write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", message], cwd=repo, check=True, capture_output=True)


class TestRebaseHappyPath:
    def test_rebase_advances_feature_onto_new_main(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        canonical = _install_canonical(make_canonical, canonical_root, name="api")
        ws = make_workspace()
        worktree_factory(canonical, ws / "api", branch="feature", base="main")
        _commit(canonical, "main-only.txt", "main\n", "advance-main")
        loc = _write_manifest(ws, repos=[("kybernetix/api", "feature", "main")])

        report = rebase_workspace(loc, _config(canonical_root), no_fetch=True)
        assert report.actions[0].action == "rebased"
        assert report.actions[0].target == "main"
        assert (ws / "api" / "main-only.txt").exists()

    def test_up_to_date_is_not_rebased(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        canonical = _install_canonical(make_canonical, canonical_root, name="api")
        ws = make_workspace()
        worktree_factory(canonical, ws / "api", branch="feature", base="main")
        loc = _write_manifest(ws, repos=[("kybernetix/api", "feature", "main")])

        report = rebase_workspace(loc, _config(canonical_root), no_fetch=True)
        assert report.actions[0].action == "up_to_date"

    def test_dry_run(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        canonical = _install_canonical(make_canonical, canonical_root, name="api")
        ws = make_workspace()
        worktree_factory(canonical, ws / "api", branch="feature", base="main")
        loc = _write_manifest(ws, repos=[("kybernetix/api", "feature", "main")])

        report = rebase_workspace(loc, _config(canonical_root), no_fetch=True, dry_run=True)
        assert report.actions[0].action == "would_rebase"


class TestRebaseConflicts:
    def test_stops_on_first_conflict_by_default(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        api = _install_canonical(make_canonical, canonical_root, name="api")
        dash = _install_canonical(make_canonical, canonical_root, name="dashboard")
        ws = make_workspace()
        worktree_factory(api, ws / "api", branch="feature", base="main")
        worktree_factory(dash, ws / "dashboard", branch="feature", base="main")

        # Set up a conflict on api.
        (ws / "api" / "README.md").write_text("feature\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=ws / "api", check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "feature-edit"],
            cwd=ws / "api",
            check=True,
            capture_output=True,
        )
        _commit(api, "README.md", "main change\n", "main-edit")

        loc = _write_manifest(
            ws,
            repos=[
                ("kybernetix/api", "feature", "main"),
                ("kybernetix/dashboard", "feature", "main"),
            ],
        )
        report = rebase_workspace(loc, _config(canonical_root), no_fetch=True)
        # api should be in conflict, dashboard skipped.
        assert report.actions[0].action == "conflict"
        assert report.actions[1].action == "skipped"
        assert report.has_conflicts is True

    def test_continue_on_error_processes_all_repos(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        api = _install_canonical(make_canonical, canonical_root, name="api")
        dash = _install_canonical(make_canonical, canonical_root, name="dashboard")
        ws = make_workspace()
        worktree_factory(api, ws / "api", branch="feature", base="main")
        worktree_factory(dash, ws / "dashboard", branch="feature", base="main")
        # Conflict on api, advance dashboard's main so its rebase succeeds.
        (ws / "api" / "README.md").write_text("feature\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=ws / "api", check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "feature-edit"],
            cwd=ws / "api",
            check=True,
            capture_output=True,
        )
        _commit(api, "README.md", "main change\n", "main-edit")
        _commit(dash, "extra.txt", "x\n", "advance-dash-main")

        loc = _write_manifest(
            ws,
            repos=[
                ("kybernetix/api", "feature", "main"),
                ("kybernetix/dashboard", "feature", "main"),
            ],
        )
        report = rebase_workspace(
            loc, _config(canonical_root), no_fetch=True, continue_on_error=True
        )
        assert report.actions[0].action == "conflict"
        assert report.actions[1].action == "rebased"


class TestRebaseWithOnto:
    def test_onto_override(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        canonical = _install_canonical(make_canonical, canonical_root, name="api")
        # Make a wip branch with one commit beyond main.
        subprocess.run(
            ["git", "branch", "wip", "main"], cwd=canonical, check=True, capture_output=True
        )
        # Add a feature worktree from main.
        ws = make_workspace()
        worktree_factory(canonical, ws / "api", branch="feature", base="main")
        # Advance wip.
        subprocess.run(["git", "checkout", "wip"], cwd=canonical, check=True, capture_output=True)
        _commit(canonical, "wip-only.txt", "w\n", "advance-wip")
        subprocess.run(["git", "checkout", "main"], cwd=canonical, check=True, capture_output=True)

        loc = _write_manifest(ws, repos=[("kybernetix/api", "feature", "main")])
        report = rebase_workspace(loc, _config(canonical_root), onto="wip", no_fetch=True)
        assert report.actions[0].action == "rebased"
        assert report.actions[0].target == "wip"
        assert (ws / "api" / "wip-only.txt").exists()


class TestRebaseGuards:
    def test_skips_when_worktree_missing(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        _install_canonical(make_canonical, canonical_root, name="api")
        ws = make_workspace()
        loc = _write_manifest(ws, repos=[("kybernetix/api", "feature", "main")])
        report = rebase_workspace(loc, _config(canonical_root), no_fetch=True)
        assert report.actions[0].action == "skipped"

    def test_set_mode_rejected(self, tmp_path: Path) -> None:
        marker = tmp_path / "brunch-set.toml"
        marker.write_text('name = "s"\n', encoding="utf-8")
        loc = WorkspaceLocation(mode="set", root=tmp_path, manifest_path=marker)
        with pytest.raises(WorkspaceNotFoundError):
            rebase_workspace(loc, ToolConfig())
