"""End-to-end safety tests for ``brunch rm``.

These exercise the deletion safety contract via the actual CLI, which is
what the user sees. Counterpart to ``tests/unit/test_services_rm_safety.py``.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tarfile
from collections.abc import Callable
from pathlib import Path

from typer.testing import CliRunner

from brunch.cli import app

runner = CliRunner()


def _install_canonical(
    make_canonical: Callable[..., Path], canonical_root: Path, *, name: str
) -> Path:
    target = canonical_root / "github.com" / "acme" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(make_canonical(name)), str(target))
    return target


def _write_config(home: Path, *, root: Path) -> None:
    cfg_dir = home / ".config" / "brunch"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.toml").write_text(f'root = "{root}"\n', encoding="utf-8")


def _setup(
    isolated_home: Path,
    canonical_root: Path,
    make_canonical: Callable[..., Path],
    *,
    name: str = "task-1",
    repos: list[str] | None = None,
) -> Path:
    for repo_name in repos or ["api"]:
        _install_canonical(make_canonical, canonical_root, name=repo_name)
    _write_config(isolated_home, root=canonical_root)
    runner.invoke(app, ["init", name, "-p", str(isolated_home)])
    ws = isolated_home / name
    for repo_name in repos or ["api"]:
        runner.invoke(app, ["add", f"acme/{repo_name}", "-w", str(ws)])
    return ws


class TestSiblingPreservation:
    """Exact reproduction of the regression that motivated M4.1."""

    def test_sibling_dir_survives_rm(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        ws = _setup(isolated_home, canonical_root, make_canonical)
        # The user's out-of-band sibling — the thing that got destroyed before.
        sibling = ws / "manually-cloned-helper"
        sibling.mkdir()
        (sibling / "important.md").write_text("do not lose me\n", encoding="utf-8")

        result = runner.invoke(app, ["rm", "-w", str(ws)])
        assert result.exit_code == 0, result.output
        assert ws.is_dir(), "workspace dir should survive when unknown content is present"
        assert (sibling / "important.md").read_text() == "do not lose me\n"
        assert "preserved 1 non-manifest item" in result.output
        assert "workspace dir preserved" in result.output

    def test_sibling_git_repo_survives_rm(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        ws = _setup(isolated_home, canonical_root, make_canonical)
        # A separate git repo dropped under the workspace.
        other = ws / "extra-clone"
        other.mkdir()
        subprocess.run(
            ["git", "init", "-q", "-b", "main"], cwd=other, check=True, capture_output=True
        )

        result = runner.invoke(app, ["rm", "-w", str(ws)])
        assert result.exit_code == 0
        assert (other / ".git").is_dir()


class TestForceWithPreserved:
    def test_force_archives_includes_preserved_and_preserves(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        ws = _setup(isolated_home, canonical_root, make_canonical)
        (ws / "scratch.md").write_text("scratch\n", encoding="utf-8")
        # Make the worktree dirty so --force is meaningful.
        (ws / "api" / "dirty.txt").write_text("dirty\n", encoding="utf-8")

        result = runner.invoke(app, ["rm", "-w", str(ws), "--force"])
        assert result.exit_code == 0, result.output
        # Sibling is still there.
        assert (ws / "scratch.md").read_text() == "scratch\n"
        # Workspace dir survives.
        assert ws.is_dir()
        # Worktree is gone.
        assert not (ws / "api").exists()
        # Archive captured both the worktree contents and the sibling.
        archive_dir = isolated_home / ".local" / "share" / "brunch" / "archives"
        archives = list(archive_dir.glob("task-1-*.tar.gz"))
        assert len(archives) == 1
        with tarfile.open(archives[0]) as tar:
            names = tar.getnames()
        assert "task-1/scratch.md" in names
        assert "task-1/api/dirty.txt" in names


class TestDryRunSurfacesPreserved:
    def test_dry_run_shows_what_would_be_preserved(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        ws = _setup(isolated_home, canonical_root, make_canonical)
        (ws / ".envrc").write_text("x\n", encoding="utf-8")
        (ws / "notes").mkdir()

        result = runner.invoke(app, ["rm", "-w", str(ws), "--dry-run", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["action"] == "partial"
        preserved_names = {Path(p).name for p in payload["preserved"]}
        assert preserved_names == {".envrc", "notes"}
        # Nothing actually changed.
        assert (ws / "api" / ".git").exists()
        assert ws.is_dir()


class TestSymlinkAtRoot:
    def test_symlink_target_is_not_followed(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        ws = _setup(isolated_home, canonical_root, make_canonical)
        outside = tmp_path / "outside-target"
        outside.mkdir()
        (outside / "secret.txt").write_text("secret\n", encoding="utf-8")
        link = ws / "external"
        link.symlink_to(outside)

        result = runner.invoke(app, ["rm", "-w", str(ws)])
        assert result.exit_code == 0
        # Symlink itself is preserved.
        assert link.is_symlink()
        # The target was never touched.
        assert (outside / "secret.txt").read_text() == "secret\n"


class TestCleanWorkspaceStillFullyRemoves:
    """The "happy path" regression test — when only manifest content is
    present, rm still fully removes the workspace."""

    def test_only_manifest_content_yields_full_removal(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        ws = _setup(isolated_home, canonical_root, make_canonical)
        result = runner.invoke(app, ["rm", "-w", str(ws), "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["action"] == "removed"
        assert payload["preserved"] == []
        assert not ws.exists()


class TestDangerousRoot:
    def test_refuses_when_w_points_at_home(self, tmp_path: Path, monkeypatch) -> None:
        # Put a workspace marker at HOME and verify the safety guard kicks in.
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))
        (fake_home / "brunch.toml").write_text('name = "evil"\n', encoding="utf-8")

        result = runner.invoke(app, ["rm", "-w", str(fake_home)])
        assert result.exit_code != 0
        assert "home directory" in result.output
        # The marker file must still be present — we refused before doing anything.
        assert (fake_home / "brunch.toml").is_file()
