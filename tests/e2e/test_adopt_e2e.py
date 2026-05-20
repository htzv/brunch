"""End-to-end tests for ``brunch adopt`` and ``brunch init --adopt``."""

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


def _hand_built_workspace(
    tmp_path: Path,
    isolated_home: Path,
    make_canonical: Callable[..., Path],
    *,
    name: str = "tech-1796",
    repos: list[str] | None = None,
) -> tuple[Path, Path]:
    """Build a workspace directory the old-fashioned way (raw git worktree add).

    No `brunch init`, no `brunch add` — the user is bringing this folder under
    brunch retroactively. Returns (workspace_path, canonical_root).
    """

    repos = repos or ["api"]
    canonical_root = tmp_path / "canonical-root"
    workspace = isolated_home / name
    workspace.mkdir(parents=True)
    _write_config(isolated_home, root=canonical_root)
    for r in repos:
        canonical = _install_canonical(make_canonical, canonical_root, name=r)
        subprocess.run(
            ["git", "worktree", "add", "-b", name, str(workspace / r), "main"],
            cwd=canonical,
            check=True,
            capture_output=True,
        )
    return workspace, canonical_root


class TestAdoptCommand:
    def test_adopts_cwd_workspace(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        ws, _ = _hand_built_workspace(
            tmp_path, isolated_home, make_canonical, repos=["api", "dashboard"]
        )

        result = runner.invoke(app, ["adopt", str(ws)])
        assert result.exit_code == 0, result.output
        assert "adopted" in result.output
        # Manifest exists with the right contents.
        manifest = ws / "brunch.toml"
        assert manifest.is_file()
        text = manifest.read_text(encoding="utf-8")
        assert 'name = "tech-1796"' in text
        assert 'repo = "acme/api"' in text
        assert 'repo = "acme/dashboard"' in text

    def test_adopt_explicit_name(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        ws, _ = _hand_built_workspace(tmp_path, isolated_home, make_canonical)
        result = runner.invoke(app, ["adopt", str(ws), "--name", "custom-name"])
        assert result.exit_code == 0
        manifest = ws / "brunch.toml"
        assert 'name = "custom-name"' in manifest.read_text()

    def test_adopt_json_shape(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        ws, _ = _hand_built_workspace(tmp_path, isolated_home, make_canonical)
        result = runner.invoke(app, ["adopt", str(ws), "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["action"] == "adopted"
        assert payload["name"] == "tech-1796"
        assert payload["discovered"][0]["repo"] == "acme/api"
        # Sync + fsck both ran and were clean.
        assert all(a["action"] != "error" for a in payload["sync_report"]["actions"])
        assert payload["fsck_report"]["findings"] == []

    def test_adopt_dry_run_writes_nothing(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        ws, _ = _hand_built_workspace(tmp_path, isolated_home, make_canonical)
        result = runner.invoke(app, ["adopt", str(ws), "--dry-run"])
        assert result.exit_code == 0
        assert "would adopt" in result.output
        assert not (ws / "brunch.toml").exists()

    def test_post_adopt_status_and_fsck_work(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        ws, _ = _hand_built_workspace(tmp_path, isolated_home, make_canonical)
        runner.invoke(app, ["adopt", str(ws)])
        # status now finds the workspace and reports clean.
        status = runner.invoke(app, ["status", "-w", str(ws), "--json"])
        assert status.exit_code == 0
        payload = json.loads(status.output)
        assert payload["repos"][0]["on_declared_branch"] is True
        # fsck passes.
        fsck = runner.invoke(app, ["fsck", "-w", str(ws)])
        assert fsck.exit_code == 0
        assert "all checks passed" in fsck.output

    def test_adopt_fails_on_canonical_outside_root(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        # Configure brunch to expect canonicals at /configured/, but the
        # actual canonical lives elsewhere.
        canonical_root = tmp_path / "configured"
        canonical_root.mkdir()
        elsewhere = tmp_path / "elsewhere"
        canonical = elsewhere / "github.com" / "acme" / "api"
        canonical.parent.mkdir(parents=True)
        shutil.move(str(make_canonical("api")), str(canonical))
        ws = isolated_home / "wandering"
        ws.mkdir()
        subprocess.run(
            ["git", "worktree", "add", "-b", "feat", str(ws / "api"), "main"],
            cwd=canonical,
            check=True,
            capture_output=True,
        )
        _write_config(isolated_home, root=canonical_root)

        result = runner.invoke(app, ["adopt", str(ws)])
        assert result.exit_code == 1
        assert "not under the configured root" in result.output
        # No partial manifest written.
        assert not (ws / "brunch.toml").exists()


class TestInitAdoptFlag:
    def test_init_adopt_is_equivalent_to_adopt(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        ws, _ = _hand_built_workspace(tmp_path, isolated_home, make_canonical, name="task-1")

        result = runner.invoke(app, ["init", "task-1", "--adopt", "-p", str(isolated_home)])
        assert result.exit_code == 0, result.output
        assert "adopted" in result.output
        assert (ws / "brunch.toml").is_file()

    def test_adopt_conflicts_with_set_or_template(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        _hand_built_workspace(tmp_path, isolated_home, make_canonical, name="task-1")
        result = runner.invoke(
            app,
            ["init", "task-1", "--adopt", "--set", "-p", str(isolated_home)],
        )
        assert result.exit_code != 0
        assert "--adopt" in result.output
