"""`br rm` keeps brunch.toml honest when it leaves the workspace directory behind."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

from brunch.manifest import load_workspace_manifest
from brunch.models import ToolConfig, WorkspaceLocation
from brunch.services.rm import rm_workspace

REPOS = [("kybernetix/api", "feat", "main"), ("kybernetix/web", "feat", "main")]


def _write_manifest(ws: Path, repos: list[tuple[str, str, str]]) -> WorkspaceLocation:
    text = f'name = "{ws.name}"\n'
    for repo, branch, base in repos:
        text += f'\n[[repo]]\nrepo = "{repo}"\nbranch = "{branch}"\nbase = "{base}"\n'
    manifest_path = ws / "brunch.toml"
    manifest_path.write_text(text, encoding="utf-8")
    return WorkspaceLocation(mode="workspace", root=ws, manifest_path=manifest_path)


def _install_canonical(
    make_canonical: Callable[..., Path], canonical_root: Path, name: str
) -> Path:
    target = canonical_root / "github.com" / "kybernetix" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(make_canonical(name)), str(target))
    return target


def _setup(
    tmp_path: Path,
    make_canonical: Callable[..., Path],
    make_workspace: Callable[..., Path],
    worktree_factory: Callable[..., None],
) -> tuple[Path, WorkspaceLocation, ToolConfig, dict[str, Path]]:
    canonical_root = tmp_path / "canonical-root"
    canonicals = {n: _install_canonical(make_canonical, canonical_root, n) for n in ("api", "web")}
    ws = make_workspace()
    for name, canonical in canonicals.items():
        worktree_factory(canonical, ws / name, branch="feat", base="main")
    config = ToolConfig(root=canonical_root, default_forge="github.com")
    return ws, _write_manifest(ws, REPOS), config, canonicals


class TestEntriesLeaveTheManifestWithTheirWorktrees:
    def test_removed_worktrees_are_dropped_when_the_directory_is_kept(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        ws, loc, config, _ = _setup(tmp_path, make_canonical, make_workspace, worktree_factory)
        (ws / "_docs").mkdir()

        outcome = rm_workspace(loc, config)

        assert outcome.action == "partial"
        manifest = load_workspace_manifest(loc.manifest_path)
        assert manifest.repos == []
        assert manifest.name == ws.name
        assert sorted(outcome.manifest_entries_dropped) == ["kybernetix/api", "kybernetix/web"]

    def test_an_already_absent_worktree_is_dropped_too(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        ws, loc, config, _ = _setup(tmp_path, make_canonical, make_workspace, worktree_factory)
        (ws / "_docs").mkdir()
        shutil.rmtree(ws / "web")

        rm_workspace(loc, config)

        assert load_workspace_manifest(loc.manifest_path).repos == []

    def test_an_entry_whose_removal_failed_stays_and_so_does_the_manifest(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        ws, loc, config, canonicals = _setup(
            tmp_path, make_canonical, make_workspace, worktree_factory
        )
        shutil.rmtree(canonicals["web"])

        outcome = rm_workspace(loc, config)

        assert outcome.action == "partial"
        assert (ws / "web").exists()
        assert not (ws / "api").exists()
        remaining = load_workspace_manifest(loc.manifest_path).repos
        assert [r.repo for r in remaining] == ["kybernetix/web"]
        assert outcome.manifest_entries_dropped == ["kybernetix/api"]

    def test_dry_run_previews_the_entries_the_real_run_drops(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        ws, loc, config, canonicals = _setup(
            tmp_path, make_canonical, make_workspace, worktree_factory
        )
        (ws / "_docs").mkdir()
        shutil.rmtree(canonicals["web"])

        preview = rm_workspace(loc, config, dry_run=True)
        real = rm_workspace(loc, config)

        assert (
            preview.manifest_entries_dropped == real.manifest_entries_dropped == ["kybernetix/api"]
        )
        assert preview.action == real.action == "partial"

    def test_dry_run_expects_a_partial_removal_when_one_will_fail(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        _, loc, config, canonicals = _setup(
            tmp_path, make_canonical, make_workspace, worktree_factory
        )
        shutil.rmtree(canonicals["web"])

        assert rm_workspace(loc, config, dry_run=True).action == "partial"

    def test_dry_run_changes_nothing(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        ws, loc, config, _ = _setup(tmp_path, make_canonical, make_workspace, worktree_factory)
        (ws / "_docs").mkdir()
        before = loc.manifest_path.read_text(encoding="utf-8")

        rm_workspace(loc, config, dry_run=True)

        assert loc.manifest_path.read_text(encoding="utf-8") == before

    def test_a_clean_removal_still_deletes_the_manifest_and_directory(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        ws, loc, config, _ = _setup(tmp_path, make_canonical, make_workspace, worktree_factory)

        outcome = rm_workspace(loc, config)

        assert outcome.action == "removed"
        assert not ws.exists()
        assert outcome.manifest_entries_dropped == []
