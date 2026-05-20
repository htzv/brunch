"""Dedicated safety test suite for ``brunch rm``.

Covers the deletion safety contract from ``docs/initial-design.md §7.5``:
brunch deletes only ``brunch.toml`` + manifest-declared worktrees +
the workspace directory itself (only when it ends up empty). Anything
else is preserved.

These tests are kept separate from ``test_services_rm.py`` so the safety
properties are easy to enumerate in one place and the suite can grow
without overwhelming the happy-path tests.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import unittest.mock
from collections.abc import Callable
from pathlib import Path

import pytest

from brunch.errors import BrunchError
from brunch.models import ToolConfig, WorkspaceLocation
from brunch.services.rm import (
    _enumerate_preserved,
    _refuse_dangerous_root,
    rm_workspace,
)


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


# ---------------------------------------------------------------------------
# The exact regression case the user just hit
# ---------------------------------------------------------------------------


class TestRegressionUserReportedSiblingNuke:
    """Reproduction of the bug that motivated M4.1.

    Workspace contained one registered worktree plus a sibling directory
    the user had created out-of-band. Pre-M4.1, ``brunch rm`` rmtree'd
    the workspace root and destroyed the sibling. Now the sibling must
    be preserved and the outcome reported as ``partial``.
    """

    def test_sibling_dir_is_preserved(
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
        # The user's out-of-band sibling.
        sibling = ws / "scratch"
        sibling.mkdir()
        (sibling / "notes.md").write_text("important\n", encoding="utf-8")

        loc = _write_manifest(ws, repos=[("acme/api", "feat", "main")])
        outcome = rm_workspace(loc, _config(canonical_root))

        assert outcome.action == "partial"
        assert sibling.is_dir()
        assert (sibling / "notes.md").read_text() == "important\n"
        # Workspace dir survives because of the sibling.
        assert ws.is_dir()
        # brunch.toml is left alongside, so a future sync/rm still works.
        assert (ws / "brunch.toml").is_file()
        # Reported in the preserved list.
        assert sibling in {p.resolve() for p in outcome.preserved}


# ---------------------------------------------------------------------------
# Per-edge-case unit coverage of preserved content
# ---------------------------------------------------------------------------


class TestPreservedContent:
    """Each kind of "unknown content" the safety contract must preserve."""

    def _setup(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> tuple[Path, WorkspaceLocation, ToolConfig]:
        canonical_root = tmp_path / "canonical-root"
        canonical = _install_canonical(make_canonical, canonical_root, name="api")
        ws = make_workspace()
        worktree_factory(canonical, ws / "api", branch="feat", base="main")
        loc = _write_manifest(ws, repos=[("acme/api", "feat", "main")])
        return ws, loc, _config(canonical_root)

    def test_sibling_file_preserved(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        ws, loc, cfg = self._setup(tmp_path, make_canonical, make_workspace, worktree_factory)
        marker = ws / "TODO.md"
        marker.write_text("read me\n", encoding="utf-8")

        outcome = rm_workspace(loc, cfg)
        assert outcome.action == "partial"
        assert marker.is_file()

    def test_hidden_file_preserved(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        ws, loc, cfg = self._setup(tmp_path, make_canonical, make_workspace, worktree_factory)
        (ws / ".envrc").write_text("export FOO=bar\n", encoding="utf-8")

        outcome = rm_workspace(loc, cfg)
        assert outcome.action == "partial"
        assert (ws / ".envrc").is_file()

    def test_hidden_dir_preserved(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        ws, loc, cfg = self._setup(tmp_path, make_canonical, make_workspace, worktree_factory)
        (ws / ".idea").mkdir()
        (ws / ".idea" / "workspace.xml").write_text("<x/>", encoding="utf-8")

        outcome = rm_workspace(loc, cfg)
        assert outcome.action == "partial"
        assert (ws / ".idea" / "workspace.xml").is_file()

    def test_sibling_git_repo_preserved(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        ws, loc, cfg = self._setup(tmp_path, make_canonical, make_workspace, worktree_factory)
        # An unrelated git repo someone manually dropped under the workspace.
        other = ws / "experiment-clone"
        other.mkdir()
        subprocess.run(
            ["git", "init", "-q", "-b", "main"], cwd=other, check=True, capture_output=True
        )
        (other / "README.md").write_text("# scratch\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=other, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "x"],
            cwd=other,
            check=True,
            capture_output=True,
        )

        outcome = rm_workspace(loc, cfg)
        assert outcome.action == "partial"
        assert (other / ".git").is_dir()
        assert (other / "README.md").read_text() == "# scratch\n"

    def test_symlink_at_root_preserved_not_followed(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        ws, loc, cfg = self._setup(tmp_path, make_canonical, make_workspace, worktree_factory)
        # Symlink whose target lives *outside* the workspace.
        outside = tmp_path / "outside-target"
        outside.mkdir()
        (outside / "secret.txt").write_text("secret\n", encoding="utf-8")
        link = ws / "external-stuff"
        link.symlink_to(outside)

        outcome = rm_workspace(loc, cfg)
        assert outcome.action == "partial"
        # The symlink survives.
        assert link.is_symlink()
        # The target survives (we never followed and removed inside).
        assert (outside / "secret.txt").read_text() == "secret\n"

    def test_nested_unknown_content_under_a_sibling_preserved(
        self,
        tmp_path: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        """Even content nested several levels deep under a preserved sibling
        must remain untouched (we don't recurse)."""

        ws, loc, cfg = self._setup(tmp_path, make_canonical, make_workspace, worktree_factory)
        deep = ws / "notes" / "a" / "b" / "c"
        deep.mkdir(parents=True)
        target_file = deep / "important.txt"
        target_file.write_text("hi\n", encoding="utf-8")

        outcome = rm_workspace(loc, cfg)
        assert outcome.action == "partial"
        assert target_file.read_text() == "hi\n"


# ---------------------------------------------------------------------------
# Happy-path negation — the partial-vs-removed boundary
# ---------------------------------------------------------------------------


class TestEmptyWorkspaceFullyRemoves:
    def test_only_brunch_toml_and_worktrees_removes_everything(
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

        outcome = rm_workspace(loc, _config(canonical_root))
        assert outcome.action == "removed"
        assert outcome.preserved == []
        assert not ws.exists()


# ---------------------------------------------------------------------------
# Force + preservation interaction
# ---------------------------------------------------------------------------


class TestForceWithPreservedContent:
    def test_force_archives_and_preserves(
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
        (ws / "scratch.md").write_text("scratch\n", encoding="utf-8")
        # Make the worktree dirty so --force is exercised.
        (ws / "api" / "dirty.txt").write_text("dirty\n", encoding="utf-8")
        loc = _write_manifest(ws, repos=[("acme/api", "feat", "main")])

        outcome = rm_workspace(loc, _config(canonical_root), force=True)
        # Forced + sibling content present → partial: archive succeeded, manifest
        # worktree was removed, but the sibling is preserved.
        assert outcome.action == "partial"
        assert outcome.archive_path is not None
        assert outcome.archive_path.is_file()
        # The sibling survives even though --force was used.
        assert (ws / "scratch.md").read_text() == "scratch\n"
        # Worktree itself is gone.
        assert not (ws / "api").exists()


# ---------------------------------------------------------------------------
# Dry-run sees preserved content too
# ---------------------------------------------------------------------------


class TestDryRunPreservedEnumeration:
    def test_dry_run_reports_preserved_without_acting(
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
        (ws / "TODO.md").write_text("x\n", encoding="utf-8")
        loc = _write_manifest(ws, repos=[("acme/api", "feat", "main")])

        outcome = rm_workspace(loc, _config(canonical_root), dry_run=True)
        assert outcome.dry_run is True
        assert outcome.action == "partial"
        assert any(p.name == "TODO.md" for p in outcome.preserved)
        # Nothing was actually removed.
        assert (ws / "api" / ".git").exists()
        assert (ws / "TODO.md").is_file()


# ---------------------------------------------------------------------------
# Archive failure fail-closed
# ---------------------------------------------------------------------------


class TestArchiveFailureFailsClosed:
    def test_archive_failure_aborts_removal(
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
        loc = _write_manifest(ws, repos=[("acme/api", "feat", "main")])

        with unittest.mock.patch(
            "brunch.services.rm.create_workspace_archive",
            side_effect=OSError("disk full"),
        ):
            with pytest.raises(BrunchError, match="failed to write archive"):
                rm_workspace(loc, _config(canonical_root), force=True)

        # Worktree still present — nothing was removed.
        assert (ws / "api" / ".git").exists()


# ---------------------------------------------------------------------------
# Dangerous-root guard
# ---------------------------------------------------------------------------


class TestDangerousRootRefusal:
    def test_filesystem_root_refused(self, tmp_path: Path) -> None:
        with pytest.raises(BrunchError, match="filesystem root"):
            _refuse_dangerous_root(Path("/"))

    def test_home_dir_refused(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        (tmp_path / "home").mkdir()
        with pytest.raises(BrunchError, match="home directory"):
            _refuse_dangerous_root(Path.home())

    @pytest.mark.parametrize("short", ["/", "/home", "/var"])
    def test_short_absolute_path_refused(self, short: str) -> None:
        with pytest.raises(BrunchError):
            _refuse_dangerous_root(Path(short))

    def test_deep_enough_path_allowed(self, tmp_path: Path) -> None:
        # tmp_path is a deep path under /tmp; should be allowed.
        target = tmp_path / "task-1"
        target.mkdir()
        _refuse_dangerous_root(target)  # no exception


# ---------------------------------------------------------------------------
# Reserved name handling (brunch.toml and the .brunch namespace)
# ---------------------------------------------------------------------------


class TestReservedNames:
    def test_brunch_toml_not_in_preserved(self, tmp_path: Path) -> None:
        (tmp_path / "brunch.toml").write_text('name = "x"\n', encoding="utf-8")
        (tmp_path / "extra.txt").write_text("y\n", encoding="utf-8")
        preserved = _enumerate_preserved(tmp_path, declared_paths=set())
        names = {p.name for p in preserved}
        assert "brunch.toml" not in names
        assert "extra.txt" in names

    def test_dot_brunch_namespace_reserved(self, tmp_path: Path) -> None:
        (tmp_path / ".brunch").mkdir()
        (tmp_path / "extra.txt").write_text("y\n", encoding="utf-8")
        preserved = _enumerate_preserved(tmp_path, declared_paths=set())
        names = {p.name for p in preserved}
        assert ".brunch" not in names
        assert "extra.txt" in names

    def test_declared_paths_excluded(self, tmp_path: Path) -> None:
        api = tmp_path / "api"
        api.mkdir()
        other = tmp_path / "scratch"
        other.mkdir()
        preserved = _enumerate_preserved(tmp_path, declared_paths={api.resolve()})
        names = {p.name for p in preserved}
        assert "api" not in names
        assert "scratch" in names


# ---------------------------------------------------------------------------
# Read-only sibling
# ---------------------------------------------------------------------------


class TestReadOnlySibling:
    def test_read_only_file_preserved_unchanged(
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
        ro = ws / "locked.txt"
        ro.write_text("locked\n", encoding="utf-8")
        os.chmod(ro, 0o444)  # read-only
        loc = _write_manifest(ws, repos=[("acme/api", "feat", "main")])

        try:
            outcome = rm_workspace(loc, _config(canonical_root))
            assert outcome.action == "partial"
            assert ro.is_file()
            assert ro.read_text() == "locked\n"
        finally:
            os.chmod(ro, 0o644)  # restore so tmp_path cleanup works
