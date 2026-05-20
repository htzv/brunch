"""End-to-end tests for `brunch fsck`."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path

from typer.testing import CliRunner

from brunch.cli import app

runner = CliRunner()


def _config_with(home: Path, *, root: Path) -> None:
    cfg_dir = home / ".config" / "brunch"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.toml").write_text(f'root = "{root}"\n', encoding="utf-8")


def _setup_clean(
    home: Path,
    make_canonical: Callable[..., Path],
    make_workspace: Callable[..., Path],
    worktree_factory: Callable[..., None],
) -> Path:
    canonical_root = home / "repos" / "brunch"
    _config_with(home, root=canonical_root)
    api_canonical = canonical_root / "github.com" / "acme" / "api"
    api_canonical.parent.mkdir(parents=True)
    shutil.move(str(make_canonical("api")), str(api_canonical))

    ws = make_workspace()
    worktree_factory(api_canonical, ws / "api", branch="feat", base="main")
    (ws / "brunch.toml").write_text(
        f'name = "{ws.name}"\n\n[[repo]]\nrepo = "acme/api"\nbranch = "feat"\nbase = "main"\n',
        encoding="utf-8",
    )
    return ws


class TestFsckE2E:
    def test_clean_workspace_exits_0(
        self,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        ws = _setup_clean(isolated_home, make_canonical, make_workspace, worktree_factory)
        result = runner.invoke(app, ["fsck", "-w", str(ws)])
        assert result.exit_code == 0, result.output
        assert "all checks passed" in result.output

    def test_missing_canonical_exits_1(
        self,
        isolated_home: Path,
        make_workspace: Callable[..., Path],
    ) -> None:
        # Point at a non-existent canonical root.
        _config_with(isolated_home, root=isolated_home / "nowhere")
        ws = make_workspace()
        (ws / "brunch.toml").write_text(
            f'name = "{ws.name}"\n\n[[repo]]\nrepo = "acme/api"\nbranch = "f"\nbase = "main"\n',
            encoding="utf-8",
        )
        result = runner.invoke(app, ["fsck", "-w", str(ws)])
        assert result.exit_code == 1
        assert "canonical-missing" in result.output

    def test_json_output(
        self,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        ws = _setup_clean(isolated_home, make_canonical, make_workspace, worktree_factory)
        result = runner.invoke(app, ["fsck", "-w", str(ws), "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["workspace_name"] == ws.name
        assert payload["findings"] == []

    def test_fix_emits_m5_notice(
        self,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        ws = _setup_clean(isolated_home, make_canonical, make_workspace, worktree_factory)
        result = runner.invoke(app, ["fsck", "-w", str(ws), "--fix"])
        # --fix prints a notice to stderr; CliRunner mixes streams by default.
        assert "M5" in result.output or "M5" in (result.stderr if hasattr(result, "stderr") else "")
        assert result.exit_code == 0
