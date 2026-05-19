from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from brunch.errors import (
    BranchConflictError,
    BrunchError,
    DuplicateRepoError,
    WorkspaceNotFoundError,
)
from brunch.manifest import load_workspace_manifest
from brunch.models import ToolConfig, WorkspaceLocation
from brunch.services.add import add_repo


def _make_workspace(
    ws: Path, *, repos: list[tuple[str, str, str]] | None = None
) -> WorkspaceLocation:
    text = f'name = "{ws.name}"\n'
    for repo, branch, base in repos or []:
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


class TestAddRepoHappyPath:
    def test_creates_worktree_and_appends_to_manifest(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        _install_canonical(make_canonical, canonical_root, name="api")
        ws = make_workspace("billing-flow")
        loc = _make_workspace(ws)

        outcome = add_repo(loc, _config(canonical_root), repo="acme/api")

        assert outcome.repo == "acme/api"
        # branch defaults to workspace name
        assert outcome.branch == "billing-flow"
        assert outcome.base == "main"
        assert outcome.worktree_path == ws / "api"
        assert (ws / "api" / ".git").exists()

        # Manifest now has the entry.
        m = load_workspace_manifest(loc.manifest_path)
        assert any(r.repo == "acme/api" and r.branch == "billing-flow" for r in m.repos)

    def test_explicit_branch_and_base_override_defaults(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        canonical = _install_canonical(make_canonical, canonical_root, name="api")
        # Make sure 'develop' branch exists in canonical for --base to work.
        import subprocess

        subprocess.run(
            ["git", "branch", "develop", "main"],
            cwd=canonical,
            check=True,
            capture_output=True,
        )
        ws = make_workspace()
        loc = _make_workspace(ws)

        outcome = add_repo(
            loc,
            _config(canonical_root),
            repo="acme/api",
            branch="custom-feature",
            base="develop",
        )
        assert outcome.branch == "custom-feature"
        assert outcome.base == "develop"

    def test_dry_run_does_not_modify_anything(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        _install_canonical(make_canonical, canonical_root, name="api")
        ws = make_workspace()
        loc = _make_workspace(ws)

        outcome = add_repo(loc, _config(canonical_root), repo="acme/api", dry_run=True)
        assert outcome.dry_run is True
        assert not (ws / "api").exists()
        # Manifest is unchanged.
        m = load_workspace_manifest(loc.manifest_path)
        assert m.repos == []


class TestAddRepoErrors:
    def test_duplicate_repo_in_manifest(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        _install_canonical(make_canonical, canonical_root, name="api")
        ws = make_workspace()
        loc = _make_workspace(ws, repos=[("acme/api", "feat", "main")])
        with pytest.raises(DuplicateRepoError, match="already in the manifest"):
            add_repo(loc, _config(canonical_root), repo="acme/api")

    def test_duplicate_short_name_in_manifest(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        _install_canonical(make_canonical, canonical_root, name="api")
        # Install another org's repo with the same short name.
        target = canonical_root / "github.com" / "other" / "api"
        target.parent.mkdir(parents=True)
        shutil.move(str(make_canonical("api-other")), str(target))

        ws = make_workspace()
        loc = _make_workspace(ws, repos=[("acme/api", "feat", "main")])
        # Pre-create the existing worktree so subdir collision is independent.
        from brunch.services.sync import sync_workspace

        sync_workspace(loc, _config(canonical_root))

        with pytest.raises(DuplicateRepoError, match="short name"):
            add_repo(loc, _config(canonical_root), repo="other/api")

    def test_missing_canonical_raises(
        self, tmp_path: Path, make_workspace: Callable[..., Path]
    ) -> None:
        ws = make_workspace()
        loc = _make_workspace(ws)
        with pytest.raises(BrunchError, match="canonical clone not found"):
            add_repo(loc, _config(tmp_path / "nowhere"), repo="acme/api")

    def test_existing_target_dir_raises(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        _install_canonical(make_canonical, canonical_root, name="api")
        ws = make_workspace()
        (ws / "api").mkdir()  # collide
        loc = _make_workspace(ws)
        with pytest.raises(BrunchError, match="already exists"):
            add_repo(loc, _config(canonical_root), repo="acme/api")

    def test_branch_already_checked_out_elsewhere(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        canonical = _install_canonical(make_canonical, canonical_root, name="api")
        worktree_factory(canonical, tmp_path / "park", branch="contested", base="main")
        ws = make_workspace()
        loc = _make_workspace(ws)
        with pytest.raises(BranchConflictError, match="already checked out"):
            add_repo(loc, _config(canonical_root), repo="acme/api", branch="contested")

    def test_set_mode_rejected(self, tmp_path: Path) -> None:
        marker = tmp_path / "brunch-set.toml"
        marker.write_text('name = "s"\n', encoding="utf-8")
        loc = WorkspaceLocation(mode="set", root=tmp_path, manifest_path=marker)
        with pytest.raises(WorkspaceNotFoundError):
            add_repo(loc, ToolConfig(), repo="acme/api")
