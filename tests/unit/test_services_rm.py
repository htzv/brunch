from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from brunch.errors import WorkspaceNotFoundError
from brunch.models import ToolConfig, WorkspaceLocation
from brunch.services.rm import rm_workspace


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


class TestRmCleanWorkspace:
    def test_removes_workspace_and_worktrees(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
        isolated_home: Path,
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        canonical = _install_canonical(make_canonical, canonical_root, name="api")
        ws = make_workspace()
        worktree_factory(canonical, ws / "api", branch="feat", base="main")
        loc = _write_manifest(ws, repos=[("kybernetix/api", "feat", "main")])

        outcome = rm_workspace(loc, _config(canonical_root))
        assert outcome.action == "removed"
        assert outcome.archive_path is None
        assert not ws.exists()
        # Branch survives in the canonical.
        result = subprocess.run(
            ["git", "branch", "--list", "feat"],
            cwd=canonical,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "feat" in result.stdout

    def test_dry_run_changes_nothing(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        canonical = _install_canonical(make_canonical, canonical_root, name="api")
        ws = make_workspace()
        worktree_factory(canonical, ws / "api", branch="feat", base="main")
        loc = _write_manifest(ws, repos=[("kybernetix/api", "feat", "main")])

        outcome = rm_workspace(loc, _config(canonical_root), dry_run=True)
        assert outcome.action == "would_remove"
        assert outcome.repo_actions[0].action == "would_remove"
        assert ws.exists()


class TestRmRefuseDirty:
    def test_uncommitted_changes_refuse(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        canonical = _install_canonical(make_canonical, canonical_root, name="api")
        ws = make_workspace()
        worktree_factory(canonical, ws / "api", branch="feat", base="main")
        (ws / "api" / "README.md").write_text("dirty\n", encoding="utf-8")
        loc = _write_manifest(ws, repos=[("kybernetix/api", "feat", "main")])

        outcome = rm_workspace(loc, _config(canonical_root))
        assert outcome.action == "refused"
        assert outcome.risks[0].has_uncommitted is True
        assert ws.exists()

    def test_untracked_files_refuse(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        canonical = _install_canonical(make_canonical, canonical_root, name="api")
        ws = make_workspace()
        worktree_factory(canonical, ws / "api", branch="feat", base="main")
        (ws / "api" / "new.txt").write_text("hi\n", encoding="utf-8")
        loc = _write_manifest(ws, repos=[("kybernetix/api", "feat", "main")])

        outcome = rm_workspace(loc, _config(canonical_root))
        assert outcome.action == "refused"
        assert outcome.risks[0].has_untracked is True

    def test_local_only_commits_refuse(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        canonical = _install_canonical(make_canonical, canonical_root, name="api")
        ws = make_workspace()
        worktree_factory(canonical, ws / "api", branch="feat", base="main")
        # Commit locally without setting an upstream.
        (ws / "api" / "local.txt").write_text("x\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=ws / "api", check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "local-only"],
            cwd=ws / "api",
            check=True,
            capture_output=True,
        )
        loc = _write_manifest(ws, repos=[("kybernetix/api", "feat", "main")])
        outcome = rm_workspace(loc, _config(canonical_root))
        assert outcome.action == "refused"
        risk = outcome.risks[0]
        assert risk.no_upstream is True
        assert risk.unpushed_commits == 1


class TestRmForce:
    def test_force_archives_and_removes(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
        isolated_home: Path,
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        canonical = _install_canonical(make_canonical, canonical_root, name="api")
        ws = make_workspace()
        worktree_factory(canonical, ws / "api", branch="feat", base="main")
        (ws / "api" / "dirty.txt").write_text("dirty\n", encoding="utf-8")
        loc = _write_manifest(ws, repos=[("kybernetix/api", "feat", "main")])

        outcome = rm_workspace(loc, _config(canonical_root), force=True)
        assert outcome.action == "removed"
        assert outcome.archive_path is not None
        assert outcome.archive_path.is_file()
        # Archive lands under the isolated XDG data dir.
        assert str(isolated_home / ".local" / "share" / "brunch") in str(outcome.archive_path)
        assert not ws.exists()

    def test_force_archives_even_when_clean(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
        isolated_home: Path,
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        canonical = _install_canonical(make_canonical, canonical_root, name="api")
        ws = make_workspace()
        worktree_factory(canonical, ws / "api", branch="feat", base="main")
        loc = _write_manifest(ws, repos=[("kybernetix/api", "feat", "main")])

        outcome = rm_workspace(loc, _config(canonical_root), force=True)
        assert outcome.action == "removed"
        assert outcome.archive_path is not None
        assert outcome.archive_path.is_file()


class TestRmGuards:
    def test_set_mode_rejected(self, tmp_path: Path) -> None:
        marker = tmp_path / "brunch-set.toml"
        marker.write_text('name = "s"\n', encoding="utf-8")
        loc = WorkspaceLocation(mode="set", root=tmp_path, manifest_path=marker)
        with pytest.raises(WorkspaceNotFoundError):
            rm_workspace(loc, ToolConfig())

    def test_empty_manifest_removes_workspace(
        self, tmp_path: Path, make_workspace: Callable[..., Path]
    ) -> None:
        ws = make_workspace()
        loc = _write_manifest(ws, repos=[])
        outcome = rm_workspace(loc, ToolConfig())
        assert outcome.action == "removed"
        assert not ws.exists()
