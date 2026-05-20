from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from brunch.errors import BrunchError
from brunch.manifest import load_workspace_manifest
from brunch.models import RepoSpec, ToolConfig
from brunch.services.adopt import (
    _read_gitdir_canonical,
    _reverse_resolve,
    adopt_workspace,
)


def _install_canonical(
    make_canonical: Callable[..., Path], canonical_root: Path, *, name: str
) -> Path:
    target = canonical_root / "github.com" / "acme" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(make_canonical(name)), str(target))
    return target


def _add_worktree(canonical: Path, target: Path, *, branch: str, base: str = "main") -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "worktree", "add", "-b", branch, str(target), base],
        cwd=canonical,
        check=True,
        capture_output=True,
    )


def _config(root: Path) -> ToolConfig:
    return ToolConfig(root=root, default_forge="github.com")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestReadGitdirCanonical:
    def test_resolves_canonical_from_worktree_marker(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical = make_canonical("api")
        wt = tmp_path / "wt"
        _add_worktree(canonical, wt, branch="feat")
        result = _read_gitdir_canonical(wt / ".git")
        assert result == canonical.resolve()

    def test_rejects_missing_prefix(self, tmp_path: Path) -> None:
        bad = tmp_path / "fake.git"
        bad.write_text("not a worktree marker\n", encoding="utf-8")
        with pytest.raises(BrunchError, match="missing 'gitdir:'"):
            _read_gitdir_canonical(bad)

    def test_rejects_unexpected_layout(self, tmp_path: Path) -> None:
        # Point gitdir somewhere that doesn't look like .git/worktrees/<id>.
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        marker = tmp_path / "bad.git"
        marker.write_text(f"gitdir: {elsewhere}\n", encoding="utf-8")
        with pytest.raises(BrunchError, match="unexpected gitdir layout"):
            _read_gitdir_canonical(marker)


class TestReverseResolve:
    def test_three_part_canonical_resolves(self, tmp_path: Path) -> None:
        root = tmp_path / "repos"
        canonical = root / "github.com" / "acme" / "api"
        canonical.mkdir(parents=True)
        spec = _reverse_resolve(canonical.resolve(), root)
        assert spec == RepoSpec(forge="github.com", org="acme", name="api")

    def test_rejects_canonical_outside_root(self, tmp_path: Path) -> None:
        root = tmp_path / "repos"
        root.mkdir()
        canonical = tmp_path / "elsewhere" / "acme" / "api"
        canonical.mkdir(parents=True)
        with pytest.raises(BrunchError, match="not under the configured root"):
            _reverse_resolve(canonical.resolve(), root)

    def test_rejects_wrong_depth(self, tmp_path: Path) -> None:
        root = tmp_path / "repos"
        # Only two components below root.
        canonical = root / "github.com" / "api"
        canonical.mkdir(parents=True)
        with pytest.raises(BrunchError, match="expected exactly"):
            _reverse_resolve(canonical.resolve(), root)


# ---------------------------------------------------------------------------
# adopt_workspace
# ---------------------------------------------------------------------------


def _setup_adoption_target(
    tmp_path: Path,
    make_canonical: Callable[..., Path],
    *,
    repos: list[tuple[str, str]],
) -> tuple[Path, Path]:
    """Build a directory at /tmp/.../task-X containing worktrees as direct children.

    Returns (target_dir, canonical_root). ``repos`` is a list of
    (repo_short_name, branch).
    """

    canonical_root = tmp_path / "canonical-root"
    target = tmp_path / "task-X"
    target.mkdir()
    for name, branch in repos:
        canonical = _install_canonical(make_canonical, canonical_root, name=name)
        _add_worktree(canonical, target / name, branch=branch)
    return target, canonical_root


class TestAdoptHappyPath:
    def test_adopts_two_worktrees(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        target, canonical_root = _setup_adoption_target(
            tmp_path,
            make_canonical,
            repos=[("api", "task-1"), ("dashboard", "task-1")],
        )

        outcome = adopt_workspace(target, name="task-1", config=_config(canonical_root))

        assert outcome.action == "adopted"
        assert outcome.skipped == []
        assert outcome.errors == []
        assert len(outcome.discovered) == 2
        # Default forge → short spec form.
        specs = {e.repo for e in outcome.discovered}
        assert specs == {"acme/api", "acme/dashboard"}
        # Manifest written.
        manifest = load_workspace_manifest(target / "brunch.toml")
        assert manifest.name == "task-1"
        assert {e.repo for e in manifest.repos} == specs
        assert all(e.base == "main" for e in manifest.repos)
        # Sync + fsck were run and clean.
        assert outcome.sync_report is not None
        assert outcome.sync_report.has_errors is False
        assert outcome.fsck_report is not None
        assert outcome.fsck_report.has_errors is False

    def test_uses_qualified_form_when_forge_isnt_default(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        canonical = canonical_root / "gitlab.internal" / "acme" / "api"
        canonical.parent.mkdir(parents=True)
        shutil.move(str(make_canonical("api")), str(canonical))
        target = tmp_path / "task-X"
        target.mkdir()
        _add_worktree(canonical, target / "api", branch="feat")

        outcome = adopt_workspace(target, name="task-X", config=_config(canonical_root))
        assert outcome.discovered[0].repo == "gitlab.internal/acme/api"

    def test_dry_run_writes_nothing(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        target, canonical_root = _setup_adoption_target(
            tmp_path,
            make_canonical,
            repos=[("api", "task-1")],
        )

        outcome = adopt_workspace(
            target, name="task-1", config=_config(canonical_root), dry_run=True
        )

        assert outcome.action == "would_adopt"
        assert outcome.dry_run is True
        assert outcome.sync_report is None
        assert outcome.fsck_report is None
        assert not (target / "brunch.toml").exists()


class TestAdoptSkipsAndErrors:
    def test_skips_regular_git_clone(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        target, canonical_root = _setup_adoption_target(
            tmp_path,
            make_canonical,
            repos=[("api", "task-1")],
        )
        # Drop a regular clone alongside (a .git *dir*, not file).
        scratch_clone = target / "scratch-clone"
        scratch_clone.mkdir()
        subprocess.run(
            ["git", "init", "-q", "-b", "main"],
            cwd=scratch_clone,
            check=True,
            capture_output=True,
        )
        outcome = adopt_workspace(target, name="task-1", config=_config(canonical_root))
        assert outcome.action == "adopted"
        assert {s.path.name for s in outcome.skipped} == {"scratch-clone"}
        assert "regular git clone" in outcome.skipped[0].reason

    def test_ignores_non_git_sibling(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        target, canonical_root = _setup_adoption_target(
            tmp_path,
            make_canonical,
            repos=[("api", "task-1")],
        )
        (target / "notes").mkdir()
        (target / "notes" / "x.md").write_text("y\n", encoding="utf-8")

        outcome = adopt_workspace(target, name="task-1", config=_config(canonical_root))
        assert outcome.action == "adopted"
        # Not in skipped — non-git subdirs are completely ignored, not surfaced.
        assert outcome.skipped == []

    def test_aborts_when_canonical_outside_root(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        # Worktree's canonical lives outside the configured root.
        canonical_root = tmp_path / "configured-root"
        canonical_root.mkdir()
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        canonical = elsewhere / "github.com" / "acme" / "api"
        canonical.parent.mkdir(parents=True)
        shutil.move(str(make_canonical("api")), str(canonical))

        target = tmp_path / "task-X"
        target.mkdir()
        _add_worktree(canonical, target / "api", branch="feat")

        outcome = adopt_workspace(target, name="task-X", config=_config(canonical_root))
        assert outcome.action == "failed"
        assert outcome.errors and "not under the configured root" in outcome.errors[0].message
        # Nothing was written.
        assert not (target / "brunch.toml").exists()

    def test_detached_head_errors(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        target, canonical_root = _setup_adoption_target(
            tmp_path,
            make_canonical,
            repos=[("api", "task-1")],
        )
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=target / "api",
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        subprocess.run(
            ["git", "checkout", "--detach", sha],
            cwd=target / "api",
            check=True,
            capture_output=True,
        )
        outcome = adopt_workspace(target, name="task-1", config=_config(canonical_root))
        assert outcome.action == "failed"
        assert any("detached HEAD" in e.message for e in outcome.errors)


class TestAdoptGuards:
    def test_missing_target(self, tmp_path: Path) -> None:
        with pytest.raises(BrunchError, match="does not exist"):
            adopt_workspace(tmp_path / "nope", name="x", config=ToolConfig())

    def test_existing_brunch_toml_refused(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        target, canonical_root = _setup_adoption_target(
            tmp_path,
            make_canonical,
            repos=[("api", "feat")],
        )
        (target / "brunch.toml").write_text('name = "preexisting"\n', encoding="utf-8")
        with pytest.raises(BrunchError, match="already exists"):
            adopt_workspace(target, name="task-X", config=_config(canonical_root))

    def test_empty_target_with_no_worktrees(self, tmp_path: Path) -> None:
        target = tmp_path / "empty"
        target.mkdir()
        with pytest.raises(BrunchError, match="no worktrees found"):
            adopt_workspace(target, name="x", config=ToolConfig())
