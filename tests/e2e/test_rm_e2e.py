"""End-to-end tests for `brunch rm`."""

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
    target = canonical_root / "github.com" / "kybernetix" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(make_canonical(name)), str(target))
    return target


def _write_config(home: Path, *, root: Path) -> None:
    cfg_dir = home / ".config" / "brunch"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.toml").write_text(f'root = "{root}"\n', encoding="utf-8")


def _setup_workspace(
    isolated_home: Path,
    canonical_root: Path,
    make_canonical: Callable[..., Path],
    *,
    name: str = "task-1",
    repos: list[str] | None = None,
) -> Path:
    repos = repos or ["api"]
    for repo_name in repos:
        _install_canonical(make_canonical, canonical_root, name=repo_name)
    _write_config(isolated_home, root=canonical_root)
    runner.invoke(app, ["init", name, "-p", str(isolated_home)])
    ws = isolated_home / name
    for repo_name in repos:
        runner.invoke(app, ["add", f"kybernetix/{repo_name}", "-w", str(ws)])
    return ws


class TestRmE2E:
    def test_clean_workspace_removes(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        ws = _setup_workspace(isolated_home, canonical_root, make_canonical, repos=["api"])
        result = runner.invoke(app, ["rm", "-w", str(ws)])
        assert result.exit_code == 0, result.output
        assert not ws.exists()
        assert "removed workspace" in result.output

    def test_dry_run(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        ws = _setup_workspace(isolated_home, canonical_root, make_canonical)
        result = runner.invoke(app, ["rm", "-w", str(ws), "--dry-run"])
        assert result.exit_code == 0
        assert ws.exists()
        assert "WOULD REMOVE" in result.output

    def test_refused_on_uncommitted(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        ws = _setup_workspace(isolated_home, canonical_root, make_canonical)
        (ws / "api" / "README.md").write_text("dirty\n", encoding="utf-8")

        result = runner.invoke(app, ["rm", "-w", str(ws)])
        assert result.exit_code == 1
        assert "refused" in result.output
        assert "uncommitted" in result.output
        assert ws.exists()

    def test_force_archives_and_removes(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        ws = _setup_workspace(isolated_home, canonical_root, make_canonical)
        # Make it dirty to ensure --force is exercised.
        (ws / "api" / "stash.txt").write_text("dirty\n", encoding="utf-8")

        result = runner.invoke(app, ["rm", "-w", str(ws), "--force"])
        assert result.exit_code == 0, result.output
        assert not ws.exists()
        # Archive landed under the isolated XDG data dir.
        archive_dir = isolated_home / ".local" / "share" / "brunch" / "archives"
        archives = list(archive_dir.glob("task-1-*.tar.gz"))
        assert len(archives) == 1
        with tarfile.open(archives[0]) as tar:
            names = tar.getnames()
        assert "task-1/brunch.toml" in names
        assert "task-1/api/stash.txt" in names

    def test_force_on_clean_still_archives(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        ws = _setup_workspace(isolated_home, canonical_root, make_canonical)

        result = runner.invoke(app, ["rm", "-w", str(ws), "--force"])
        assert result.exit_code == 0, result.output
        assert not ws.exists()
        archive_dir = isolated_home / ".local" / "share" / "brunch" / "archives"
        assert list(archive_dir.glob("task-1-*.tar.gz"))

    def test_json_output_shape(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        ws = _setup_workspace(isolated_home, canonical_root, make_canonical)

        result = runner.invoke(app, ["rm", "-w", str(ws), "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["action"] == "removed"
        assert payload["forced"] is False
        assert payload["archive_path"] is None
        assert payload["repo_actions"][0]["action"] == "removed"

    def test_branch_survives_in_canonical(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        ws = _setup_workspace(isolated_home, canonical_root, make_canonical)
        result = runner.invoke(app, ["rm", "-w", str(ws)])
        assert result.exit_code == 0
        canonical = canonical_root / "github.com" / "kybernetix" / "api"
        out = subprocess.run(
            ["git", "branch", "--list", "task-1"],
            cwd=canonical,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        # Branch name appears in the output.
        assert "task-1" in out

    def test_idempotent_after_first_run(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        ws = _setup_workspace(isolated_home, canonical_root, make_canonical)
        runner.invoke(app, ["rm", "-w", str(ws)])
        # Re-running on a now-missing workspace exits 3 (WorkspaceNotFound),
        # because discovery walks up from a path that no longer has a marker.
        result = runner.invoke(app, ["rm", "-w", str(ws.parent)])
        assert result.exit_code == 3
