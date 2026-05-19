"""End-to-end tests for the M2 mutation flow: init → add → sync."""

from __future__ import annotations

import json
import shutil
import subprocess
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


def _install_template(home: Path, template_id: str, body: str) -> None:
    target = home / ".config" / "brunch" / "templates"
    target.mkdir(parents=True, exist_ok=True)
    (target / f"{template_id}.toml").write_text(body, encoding="utf-8")


class TestInitE2E:
    def test_init_creates_workspace_dir(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["init", "task-1", "-p", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert (tmp_path / "task-1" / "brunch.toml").is_file()
        assert "task-1" in result.output

    def test_init_set_creates_set_dir(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["init", "set-1", "--set", "-p", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert (tmp_path / "set-1" / "brunch-set.toml").is_file()

    def test_init_dry_run_creates_nothing(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["init", "task-1", "-p", str(tmp_path), "--dry-run"])
        assert result.exit_code == 0
        assert not (tmp_path / "task-1").exists()
        assert "would create" in result.output

    def test_init_refuses_existing_dir(self, tmp_path: Path) -> None:
        (tmp_path / "task-1").mkdir()
        result = runner.invoke(app, ["init", "task-1", "-p", str(tmp_path)])
        assert result.exit_code == 9  # TargetExistsError
        assert "already exists" in result.output

    def test_init_from_template_materialises_worktrees(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        _install_canonical(make_canonical, canonical_root, name="api")
        _install_canonical(make_canonical, canonical_root, name="dashboard")
        _write_config(isolated_home, root=canonical_root)
        _install_template(
            isolated_home,
            "fullstack",
            """
            description = "backend + dashboard"
            [[repo]]
            repo = "acme/api"
            [[repo]]
            repo = "acme/dashboard"
            """,
        )

        result = runner.invoke(
            app,
            [
                "init",
                "task-billing",
                "-t",
                "fullstack",
                "-p",
                str(isolated_home),
            ],
        )
        assert result.exit_code == 0, result.output
        ws = isolated_home / "task-billing"
        assert (ws / "api" / ".git").exists()
        assert (ws / "dashboard" / ".git").exists()
        assert "CREATED" in result.output


class TestAddE2E:
    def test_add_appends_to_manifest_and_creates_worktree(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        _install_canonical(make_canonical, canonical_root, name="api")
        _write_config(isolated_home, root=canonical_root)

        # First init.
        result = runner.invoke(app, ["init", "task-1", "-p", str(isolated_home)])
        assert result.exit_code == 0
        ws = isolated_home / "task-1"

        # Then add.
        result = runner.invoke(app, ["add", "acme/api", "-w", str(ws)])
        assert result.exit_code == 0, result.output
        assert (ws / "api" / ".git").exists()

        # Verify manifest content via status.
        result = runner.invoke(app, ["status", "-w", str(ws), "--json"])
        payload = json.loads(result.output)
        assert len(payload["repos"]) == 1
        assert payload["repos"][0]["short_name"] == "api"
        # Branch defaults to workspace name.
        assert payload["repos"][0]["current_branch"] == "task-1"

    def test_add_dry_run_does_nothing(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        _install_canonical(make_canonical, canonical_root, name="api")
        _write_config(isolated_home, root=canonical_root)
        runner.invoke(app, ["init", "task-1", "-p", str(isolated_home)])
        ws = isolated_home / "task-1"

        result = runner.invoke(app, ["add", "acme/api", "-w", str(ws), "--dry-run"])
        assert result.exit_code == 0
        assert not (ws / "api").exists()
        assert "would add" in result.output


class TestSyncE2E:
    def test_sync_materialises_missing_worktrees(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        _install_canonical(make_canonical, canonical_root, name="api")
        _write_config(isolated_home, root=canonical_root)

        ws = isolated_home / "task-1"
        ws.mkdir()
        (ws / "brunch.toml").write_text(
            'name = "task-1"\n\n[[repo]]\nrepo = "acme/api"\nbranch = "feat"\nbase = "main"\n',
            encoding="utf-8",
        )

        result = runner.invoke(app, ["sync", "-w", str(ws)])
        assert result.exit_code == 0, result.output
        assert (ws / "api" / ".git").exists()
        assert "CREATED" in result.output

    def test_sync_idempotent(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        _install_canonical(make_canonical, canonical_root, name="api")
        _write_config(isolated_home, root=canonical_root)
        runner.invoke(app, ["init", "task-1", "-p", str(isolated_home)])
        ws = isolated_home / "task-1"
        runner.invoke(app, ["add", "acme/api", "-w", str(ws)])

        result = runner.invoke(app, ["sync", "-w", str(ws)])
        assert result.exit_code == 0
        assert "OK" in result.output

    def test_sync_dry_run_changes_nothing(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        _install_canonical(make_canonical, canonical_root, name="api")
        _write_config(isolated_home, root=canonical_root)

        ws = isolated_home / "task-1"
        ws.mkdir()
        (ws / "brunch.toml").write_text(
            'name = "task-1"\n\n[[repo]]\nrepo = "acme/api"\nbranch = "feat"\nbase = "main"\n',
            encoding="utf-8",
        )

        result = runner.invoke(app, ["sync", "-w", str(ws), "--dry-run"])
        assert result.exit_code == 0
        assert not (ws / "api").exists()
        assert "would create" in result.output

    def test_sync_reports_branch_drift_as_warning(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        _install_canonical(make_canonical, canonical_root, name="api")
        _write_config(isolated_home, root=canonical_root)
        runner.invoke(app, ["init", "task-1", "-p", str(isolated_home)])
        ws = isolated_home / "task-1"
        runner.invoke(app, ["add", "acme/api", "-w", str(ws)])

        # Switch the worktree to a different branch.
        subprocess.run(
            ["git", "checkout", "-b", "other"],
            cwd=ws / "api",
            check=True,
            capture_output=True,
        )

        result = runner.invoke(app, ["sync", "-w", str(ws)])
        assert "WARNING" in result.output
        assert "other" in result.output


class TestEndToEndFlow:
    def test_init_add_sync_status_fsck(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        _install_canonical(make_canonical, canonical_root, name="api")
        _install_canonical(make_canonical, canonical_root, name="dashboard")
        _write_config(isolated_home, root=canonical_root)

        # init
        assert runner.invoke(app, ["init", "billing-flow", "-p", str(isolated_home)]).exit_code == 0
        ws = isolated_home / "billing-flow"

        # add two repos
        assert runner.invoke(app, ["add", "acme/api", "-w", str(ws)]).exit_code == 0
        assert runner.invoke(app, ["add", "acme/dashboard", "-w", str(ws)]).exit_code == 0

        # status / sync / fsck all green
        s = runner.invoke(app, ["status", "-w", str(ws), "--json"])
        assert s.exit_code == 0
        payload = json.loads(s.output)
        assert len(payload["repos"]) == 2
        assert all(r["on_declared_branch"] for r in payload["repos"])

        assert runner.invoke(app, ["sync", "-w", str(ws)]).exit_code == 0
        assert runner.invoke(app, ["fsck", "-w", str(ws)]).exit_code == 0
