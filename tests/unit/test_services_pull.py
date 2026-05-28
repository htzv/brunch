from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from brunch.errors import WorkspaceNotFoundError
from brunch.models import ToolConfig, WorkspaceLocation
from brunch.services.pull import pull_workspace


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


class TestPullWorkspace:
    def test_pull_brings_in_remote_commits(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
    ) -> None:
        # Set up an upstream, a canonical that clones it, and a worktree on main.
        canonical_root = tmp_path / "canonical-root"
        upstream = make_canonical("upstream-target")
        # Clone upstream into the canonical location.
        canonical = canonical_root / "github.com" / "kybernetix" / "api"
        canonical.parent.mkdir(parents=True)
        subprocess.run(
            ["git", "clone", str(upstream), str(canonical)],
            check=True,
            capture_output=True,
        )

        ws = make_workspace()
        # Add a worktree on a branch that tracks origin/main so `git pull`
        # has a well-defined upstream and can fast-forward.
        subprocess.run(
            ["git", "worktree", "add", "-b", "tracking-main", str(ws / "api"), "main"],
            cwd=canonical,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "branch", "--set-upstream-to=origin/main", "tracking-main"],
            cwd=ws / "api",
            check=True,
            capture_output=True,
        )

        # Advance upstream.
        (upstream / "new.txt").write_text("hi\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=upstream, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "upstream-commit"],
            cwd=upstream,
            check=True,
            capture_output=True,
        )

        loc = _write_manifest(ws, repos=[("kybernetix/api", "tracking-main", "main")])
        report = pull_workspace(loc, _config(canonical_root))
        assert report.actions[0].action == "pulled"
        assert (ws / "api" / "new.txt").exists()

    def test_skips_when_no_remote(
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

        report = pull_workspace(loc, _config(canonical_root))
        assert report.actions[0].action == "skipped"

    def test_dry_run(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        upstream = make_canonical("upstream-target")
        canonical = _install_canonical(make_canonical, canonical_root, name="api")
        subprocess.run(
            ["git", "remote", "add", "origin", str(upstream)],
            cwd=canonical,
            check=True,
            capture_output=True,
        )
        ws = make_workspace()
        worktree_factory(canonical, ws / "api", branch="feat", base="main")
        loc = _write_manifest(ws, repos=[("kybernetix/api", "feat", "main")])

        report = pull_workspace(loc, _config(canonical_root), dry_run=True)
        assert report.actions[0].action == "would_pull"

    def test_set_mode_rejected(self, tmp_path: Path) -> None:
        marker = tmp_path / "brunch-set.toml"
        marker.write_text('name = "s"\n', encoding="utf-8")
        loc = WorkspaceLocation(mode="set", root=tmp_path, manifest_path=marker)
        with pytest.raises(WorkspaceNotFoundError):
            pull_workspace(loc, ToolConfig())
