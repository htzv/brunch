"""End-to-end tests for the M3 cross-repo commands."""

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


def _commit(repo: Path, filename: str, content: str, message: str) -> None:
    (repo / filename).write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", message], cwd=repo, check=True, capture_output=True)


class TestFetchE2E:
    def test_fetch_skips_without_remote(
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

        result = runner.invoke(app, ["fetch", "-w", str(ws)])
        assert result.exit_code == 0, result.output
        assert "SKIPPED" in result.output

    def test_fetch_json_output(
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

        result = runner.invoke(app, ["fetch", "-w", str(ws), "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["workspace_name"] == "task-1"
        assert payload["actions"][0]["action"] == "skipped"


class TestRebaseE2E:
    def test_rebase_linear_succeeds(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        canonical = _install_canonical(make_canonical, canonical_root, name="api")
        _write_config(isolated_home, root=canonical_root)
        runner.invoke(app, ["init", "task-1", "-p", str(isolated_home)])
        ws = isolated_home / "task-1"
        runner.invoke(app, ["add", "acme/api", "-w", str(ws)])
        # Advance main in the canonical.
        _commit(canonical, "main-only.txt", "x\n", "advance-main")

        result = runner.invoke(app, ["rebase", "-w", str(ws), "--no-fetch"])
        assert result.exit_code == 0, result.output
        assert "REBASED" in result.output
        assert (ws / "api" / "main-only.txt").exists()

    def test_rebase_up_to_date(
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

        result = runner.invoke(app, ["rebase", "-w", str(ws), "--no-fetch"])
        assert result.exit_code == 0
        assert "UP TO DATE" in result.output

    def test_rebase_conflict_stops_run(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        canonical = _install_canonical(make_canonical, canonical_root, name="api")
        _write_config(isolated_home, root=canonical_root)
        runner.invoke(app, ["init", "task-1", "-p", str(isolated_home)])
        ws = isolated_home / "task-1"
        runner.invoke(app, ["add", "acme/api", "-w", str(ws)])

        # Conflict: edit README on the feature branch and on main.
        (ws / "api" / "README.md").write_text("feature\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=ws / "api", check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "feature-edit"],
            cwd=ws / "api",
            check=True,
            capture_output=True,
        )
        _commit(canonical, "README.md", "main change\n", "main-edit")

        result = runner.invoke(app, ["rebase", "-w", str(ws), "--no-fetch"])
        assert result.exit_code == 1
        assert "CONFLICT" in result.output


class TestForeachE2E:
    def test_foreach_streaming_success(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        _install_canonical(make_canonical, canonical_root, name="api")
        _install_canonical(make_canonical, canonical_root, name="dashboard")
        _write_config(isolated_home, root=canonical_root)
        runner.invoke(app, ["init", "task-1", "-p", str(isolated_home)])
        ws = isolated_home / "task-1"
        runner.invoke(app, ["add", "acme/api", "-w", str(ws)])
        runner.invoke(app, ["add", "acme/dashboard", "-w", str(ws)])

        result = runner.invoke(app, ["foreach", "-w", str(ws), "true"])
        assert result.exit_code == 0, result.output
        # Two OK rows in the summary.
        assert result.output.count("OK") >= 2

    def test_foreach_json_captures_output(
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

        result = runner.invoke(
            app, ["foreach", "-w", str(ws), "--json", "--", "sh", "-c", "echo hello"]
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["actions"][0]["stdout"]
        assert "hello" in payload["actions"][0]["stdout"]

    def test_foreach_failure_aggregation(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        _install_canonical(make_canonical, canonical_root, name="api")
        _install_canonical(make_canonical, canonical_root, name="dashboard")
        _write_config(isolated_home, root=canonical_root)
        runner.invoke(app, ["init", "task-1", "-p", str(isolated_home)])
        ws = isolated_home / "task-1"
        runner.invoke(app, ["add", "acme/api", "-w", str(ws)])
        runner.invoke(app, ["add", "acme/dashboard", "-w", str(ws)])

        result = runner.invoke(
            app,
            ["foreach", "-w", str(ws), "--continue-on-error", "--json", "false"],
        )
        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert all(a["action"] == "failed" for a in payload["actions"])
