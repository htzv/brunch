"""Tests for `br drop` — single-repo worktree removal.

Uses real git in temp dirs (same strategy as the rm tests): a canonical clone
under a ghq-style root, worktrees added off it, and a real brunch.toml.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from brunch.errors import BrunchError, WorkspaceNotFoundError
from brunch.models import ToolConfig, WorkspaceLocation
from brunch.services.drop import drop_repo


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


def _manifest_repos(loc: WorkspaceLocation) -> list[str]:
    from brunch.manifest import load_workspace_manifest

    return [r.repo for r in load_workspace_manifest(loc.manifest_path).repos]


class TestDropClean:
    def test_drops_worktree_and_entry_keeps_siblings(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        root = tmp_path / "canonical-root"
        api = _install_canonical(make_canonical, root, name="api")
        _install_canonical(make_canonical, root, name="dashboard")
        ws = make_workspace()
        worktree_factory(api, ws / "api", branch="feat", base="main")
        worktree_factory(
            root / "github.com" / "kybernetix" / "dashboard",
            ws / "dashboard",
            branch="feat",
            base="main",
        )
        loc = _write_manifest(
            ws, repos=[("kybernetix/api", "feat", "main"), ("kybernetix/dashboard", "feat", "main")]
        )

        outcome = drop_repo(loc, _config(root), "api")
        assert outcome.action == "dropped"
        assert not (ws / "api").exists()
        assert (ws / "dashboard").exists()  # sibling untouched
        assert _manifest_repos(loc) == ["kybernetix/dashboard"]
        # branch survives in the canonical
        r = subprocess.run(
            ["git", "branch", "--list", "feat"], cwd=api, capture_output=True, text=True, check=True
        )
        assert "feat" in r.stdout

    def test_dry_run_changes_nothing(
        self, tmp_path, make_canonical, make_workspace, worktree_factory
    ) -> None:
        root = tmp_path / "canonical-root"
        api = _install_canonical(make_canonical, root, name="api")
        ws = make_workspace()
        worktree_factory(api, ws / "api", branch="feat", base="main")
        loc = _write_manifest(ws, repos=[("kybernetix/api", "feat", "main")])

        outcome = drop_repo(loc, _config(root), "api", dry_run=True)
        assert outcome.action == "would_drop"
        assert (ws / "api").exists()
        assert _manifest_repos(loc) == ["kybernetix/api"]

    def test_resolves_by_full_spec(
        self, tmp_path, make_canonical, make_workspace, worktree_factory
    ) -> None:
        root = tmp_path / "canonical-root"
        api = _install_canonical(make_canonical, root, name="api")
        ws = make_workspace()
        worktree_factory(api, ws / "api", branch="feat", base="main")
        loc = _write_manifest(ws, repos=[("kybernetix/api", "feat", "main")])

        outcome = drop_repo(loc, _config(root), "kybernetix/api")
        assert outcome.action == "dropped"

    def test_worktree_already_absent_still_drops_entry(
        self, tmp_path, make_canonical, make_workspace
    ) -> None:
        root = tmp_path / "canonical-root"
        _install_canonical(make_canonical, root, name="api")
        ws = make_workspace()  # no worktree created on disk
        loc = _write_manifest(ws, repos=[("kybernetix/api", "feat", "main")])

        outcome = drop_repo(loc, _config(root), "api")
        assert outcome.action == "dropped"
        assert _manifest_repos(loc) == []


class TestDropRefuseDirty:
    def _dirty_ws(self, tmp_path, make_canonical, make_workspace, worktree_factory, mutate):
        root = tmp_path / "canonical-root"
        api = _install_canonical(make_canonical, root, name="api")
        ws = make_workspace()
        worktree_factory(api, ws / "api", branch="feat", base="main")
        mutate(ws / "api")
        loc = _write_manifest(ws, repos=[("kybernetix/api", "feat", "main")])
        return loc, root, ws

    def test_uncommitted_refused(self, tmp_path, make_canonical, make_workspace, worktree_factory):
        loc, root, ws = self._dirty_ws(
            tmp_path,
            make_canonical,
            make_workspace,
            worktree_factory,
            lambda wt: (wt / "README.md").write_text("dirty\n", encoding="utf-8"),
        )
        outcome = drop_repo(loc, _config(root), "api")
        assert outcome.action == "refused"
        assert outcome.risk is not None and outcome.risk.has_uncommitted
        assert (ws / "api").exists()
        assert _manifest_repos(loc) == ["kybernetix/api"]

    def test_untracked_refused(self, tmp_path, make_canonical, make_workspace, worktree_factory):
        loc, root, _ws = self._dirty_ws(
            tmp_path,
            make_canonical,
            make_workspace,
            worktree_factory,
            lambda wt: (wt / "new.txt").write_text("hi\n", encoding="utf-8"),
        )
        outcome = drop_repo(loc, _config(root), "api")
        assert outcome.action == "refused"
        assert outcome.risk is not None and outcome.risk.has_untracked

    def test_local_only_commits_refused(
        self, tmp_path, make_canonical, make_workspace, worktree_factory
    ):
        def _commit(wt: Path) -> None:
            (wt / "local.txt").write_text("x\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=wt, check=True, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", "local"], cwd=wt, check=True, capture_output=True
            )

        loc, root, _ws = self._dirty_ws(
            tmp_path, make_canonical, make_workspace, worktree_factory, _commit
        )
        outcome = drop_repo(loc, _config(root), "api")
        assert outcome.action == "refused"
        assert outcome.risk is not None
        assert outcome.risk.no_upstream and outcome.risk.unpushed_commits == 1

    def test_force_drops_dirty(self, tmp_path, make_canonical, make_workspace, worktree_factory):
        loc, root, ws = self._dirty_ws(
            tmp_path,
            make_canonical,
            make_workspace,
            worktree_factory,
            lambda wt: (wt / "README.md").write_text("dirty\n", encoding="utf-8"),
        )
        outcome = drop_repo(loc, _config(root), "api", force=True)
        assert outcome.action == "dropped"
        assert not (ws / "api").exists()
        assert _manifest_repos(loc) == []


class TestDropErrors:
    def test_unknown_repo_raises(self, tmp_path, make_workspace):
        ws = make_workspace()
        loc = _write_manifest(ws, repos=[("kybernetix/api", "feat", "main")])
        with pytest.raises(BrunchError, match="not in this workspace"):
            drop_repo(loc, _config(tmp_path), "nope")

    def test_set_mode_rejected(self, tmp_path):
        marker = tmp_path / "brunch-set.toml"
        marker.write_text('name = "s"\n', encoding="utf-8")
        loc = WorkspaceLocation(mode="set", root=tmp_path, manifest_path=marker)
        with pytest.raises(WorkspaceNotFoundError):
            drop_repo(loc, ToolConfig(), "api")

    def test_missing_canonical_reports_error(
        self, tmp_path, make_workspace, worktree_factory, make_canonical
    ):
        # Build a worktree, then remove the canonical so `git worktree remove` can't run.
        root = tmp_path / "canonical-root"
        api = _install_canonical(make_canonical, root, name="api")
        ws = make_workspace()
        worktree_factory(api, ws / "api", branch="feat", base="main")
        loc = _write_manifest(ws, repos=[("kybernetix/api", "feat", "main")])
        shutil.rmtree(api)

        outcome = drop_repo(loc, _config(root), "api")
        assert outcome.action == "error"
        assert "canonical" in (outcome.message or "")
        # manifest entry left intact on error
        assert _manifest_repos(loc) == ["kybernetix/api"]
