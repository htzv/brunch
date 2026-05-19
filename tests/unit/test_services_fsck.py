from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from brunch.errors import WorkspaceNotFoundError
from brunch.models import ToolConfig, WorkspaceLocation
from brunch.services.fsck import fsck_workspace


def _write_manifest(ws: Path, *, repos: list[tuple[str, str, str]]) -> WorkspaceLocation:
    """Materialise a brunch.toml under ``ws`` and return its WorkspaceLocation."""

    text = f'name = "{ws.name}"\n'
    for repo, branch, base in repos:
        text += f'\n[[repo]]\nrepo = "{repo}"\nbranch = "{branch}"\nbase = "{base}"\n'
    manifest_path = ws / "brunch.toml"
    manifest_path.write_text(text, encoding="utf-8")
    return WorkspaceLocation(mode="workspace", root=ws, manifest_path=manifest_path)


def _config_for(canonical_root: Path) -> ToolConfig:
    return ToolConfig(root=canonical_root, default_forge="github.com")


def _findings_by_code(findings) -> dict[str, list]:
    out: dict[str, list] = {}
    for f in findings:
        out.setdefault(f.code, []).append(f)
    return out


class TestFsckHappyPath:
    def test_clean_workspace_has_no_findings(
        self,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
        tmp_path: Path,
    ) -> None:
        # Lay out a canonical at the expected ghq-style path.
        canonical_root = tmp_path / "canonical-root"
        api_canonical = canonical_root / "github.com" / "acme" / "api"
        api_canonical.parent.mkdir(parents=True)
        shutil.move(str(make_canonical("api")), str(api_canonical))

        ws = make_workspace("clean-ws")
        worktree_factory(api_canonical, ws / "api", branch="feat", base="main")
        loc = _write_manifest(ws, repos=[("acme/api", "feat", "main")])

        report = fsck_workspace(loc, _config_for(canonical_root))
        assert report.findings == []
        assert report.has_errors is False
        assert report.has_warnings is False


class TestFsckCanonicalChecks:
    def test_canonical_missing(self, make_workspace: Callable[..., Path], tmp_path: Path) -> None:
        ws = make_workspace("ws")
        loc = _write_manifest(ws, repos=[("acme/missing-repo", "f", "main")])
        report = fsck_workspace(loc, _config_for(tmp_path / "nowhere"))
        codes = _findings_by_code(report.findings)
        assert "canonical-missing" in codes
        assert report.has_errors

    def test_canonical_not_a_repo(
        self, make_workspace: Callable[..., Path], tmp_path: Path
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        fake = canonical_root / "github.com" / "acme" / "api"
        fake.mkdir(parents=True)
        # No git init: directory exists, but not a repo.
        ws = make_workspace("ws")
        loc = _write_manifest(ws, repos=[("acme/api", "f", "main")])
        report = fsck_workspace(loc, _config_for(canonical_root))
        codes = _findings_by_code(report.findings)
        assert "canonical-not-a-repo" in codes


class TestFsckWorktreeChecks:
    def test_worktree_missing(
        self,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        tmp_path: Path,
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        api_canonical = canonical_root / "github.com" / "acme" / "api"
        api_canonical.parent.mkdir(parents=True)
        shutil.move(str(make_canonical("api")), str(api_canonical))

        ws = make_workspace("ws")
        loc = _write_manifest(ws, repos=[("acme/api", "feat", "main")])
        report = fsck_workspace(loc, _config_for(canonical_root))
        codes = _findings_by_code(report.findings)
        assert "worktree-missing" in codes

    def test_branch_drift_is_a_warning(
        self,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
        tmp_path: Path,
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        api_canonical = canonical_root / "github.com" / "acme" / "api"
        api_canonical.parent.mkdir(parents=True)
        shutil.move(str(make_canonical("api")), str(api_canonical))

        ws = make_workspace("ws")
        worktree_factory(api_canonical, ws / "api", branch="actual", base="main")
        loc = _write_manifest(ws, repos=[("acme/api", "declared", "main")])
        report = fsck_workspace(loc, _config_for(canonical_root))
        codes = _findings_by_code(report.findings)
        assert "branch-drift" in codes
        assert codes["branch-drift"][0].severity == "warning"
        assert not report.has_errors


class TestFsckCanonicalWideChecks:
    def test_dangling_worktree_ref(
        self,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
        tmp_path: Path,
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        api_canonical = canonical_root / "github.com" / "acme" / "api"
        api_canonical.parent.mkdir(parents=True)
        shutil.move(str(make_canonical("api")), str(api_canonical))

        # Create a worktree somewhere, then yank its path out from under git.
        elsewhere = tmp_path / "to-be-deleted"
        worktree_factory(api_canonical, elsewhere, branch="orphan", base="main")
        shutil.rmtree(elsewhere)

        ws = make_workspace("ws")
        # Manifest references the same canonical so we exercise its worktree-list.
        worktree_factory(api_canonical, ws / "api", branch="alive", base="main")
        loc = _write_manifest(ws, repos=[("acme/api", "alive", "main")])
        report = fsck_workspace(loc, _config_for(canonical_root))
        codes = _findings_by_code(report.findings)
        assert "dangling-worktree-ref" in codes


class TestFsckExtraSubdirs:
    def test_extra_worktree_subdir_flagged(
        self,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
        tmp_path: Path,
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        api_canonical = canonical_root / "github.com" / "acme" / "api"
        api_canonical.parent.mkdir(parents=True)
        shutil.move(str(make_canonical("api")), str(api_canonical))

        ws = make_workspace("ws")
        worktree_factory(api_canonical, ws / "api", branch="feat", base="main")
        # Add a stray worktree that the manifest doesn't know about.
        worktree_factory(api_canonical, ws / "stray", branch="stray", base="main")

        loc = _write_manifest(ws, repos=[("acme/api", "feat", "main")])
        report = fsck_workspace(loc, _config_for(canonical_root))
        codes = _findings_by_code(report.findings)
        assert "extra-worktree" in codes
        assert codes["extra-worktree"][0].severity == "warning"

    def test_non_git_subdir_is_ignored(
        self,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
        tmp_path: Path,
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        api_canonical = canonical_root / "github.com" / "acme" / "api"
        api_canonical.parent.mkdir(parents=True)
        shutil.move(str(make_canonical("api")), str(api_canonical))

        ws = make_workspace("ws")
        worktree_factory(api_canonical, ws / "api", branch="feat", base="main")
        (ws / "notes").mkdir()
        (ws / "notes" / "README.md").write_text("just notes\n", encoding="utf-8")
        loc = _write_manifest(ws, repos=[("acme/api", "feat", "main")])
        report = fsck_workspace(loc, _config_for(canonical_root))
        codes = _findings_by_code(report.findings)
        assert "extra-worktree" not in codes


class TestFsckRejectsSetMode:
    def test_set_mode_rejected(self, tmp_path: Path) -> None:
        marker = tmp_path / "brunch-set.toml"
        marker.write_text('name = "s"\n', encoding="utf-8")
        loc = WorkspaceLocation(mode="set", root=tmp_path, manifest_path=marker)
        with pytest.raises(WorkspaceNotFoundError, match="set roots"):
            fsck_workspace(loc, ToolConfig())
