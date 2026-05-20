from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from brunch.errors import WorkspaceNotFoundError
from brunch.models import ToolConfig, WorkspaceLocation
from brunch.services.fetch import fetch_workspace


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


def _wire_origin(repo: Path, upstream: Path) -> None:
    subprocess.run(
        ["git", "remote", "add", "origin", str(upstream)],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def _config(root: Path) -> ToolConfig:
    return ToolConfig(root=root, default_forge="github.com")


class TestFetchWorkspace:
    def test_fetches_when_remote_configured(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        upstream = make_canonical("upstream-target")
        canonical = _install_canonical(make_canonical, canonical_root, name="api")
        _wire_origin(canonical, upstream)
        ws = make_workspace()
        worktree_factory(canonical, ws / "api", branch="feat", base="main")
        loc = _write_manifest(ws, repos=[("acme/api", "feat", "main")])

        report = fetch_workspace(loc, _config(canonical_root))
        assert report.actions[0].action == "fetched"
        assert not report.has_errors

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
        loc = _write_manifest(ws, repos=[("acme/api", "feat", "main")])

        report = fetch_workspace(loc, _config(canonical_root))
        assert report.actions[0].action == "skipped"
        assert "no remote" in report.actions[0].message

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

        report = fetch_workspace(loc, _config(canonical_root))
        assert report.actions[0].action == "skipped"
        assert "worktree missing" in report.actions[0].message

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
        _wire_origin(canonical, upstream)
        ws = make_workspace()
        worktree_factory(canonical, ws / "api", branch="feat", base="main")
        loc = _write_manifest(ws, repos=[("acme/api", "feat", "main")])

        report = fetch_workspace(loc, _config(canonical_root), dry_run=True)
        assert report.dry_run is True
        assert report.actions[0].action == "would_fetch"

    def test_set_mode_rejected(self, tmp_path: Path) -> None:
        marker = tmp_path / "brunch-set.toml"
        marker.write_text('name = "s"\n', encoding="utf-8")
        loc = WorkspaceLocation(mode="set", root=tmp_path, manifest_path=marker)
        with pytest.raises(WorkspaceNotFoundError):
            fetch_workspace(loc, ToolConfig())
