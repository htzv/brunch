"""End-to-end tests for `brunch status`.

These exercise the full controller path: CliRunner → Typer → discovery →
config loading → service → renderer.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path

from typer.testing import CliRunner

from brunch.cli import app

runner = CliRunner()


def _config_with(home: Path, *, root: Path, default_forge: str = "github.com") -> None:
    cfg_dir = home / ".config" / "brunch"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.toml").write_text(
        f'root = "{root}"\ndefault_forge = "{default_forge}"\n',
        encoding="utf-8",
    )


def _setup_workspace(
    *,
    home: Path,
    canonical_factory: Callable[..., Path],
    workspace_factory: Callable[..., Path],
    worktree_factory: Callable[..., None],
    repos: list[tuple[str, str, str]],
) -> Path:
    """Build a realistic workspace under ``home`` and return its path.

    Each ``(spec, branch, base)`` triple becomes a canonical clone at the
    ghq-style path plus a worktree under the workspace directory.
    """

    canonical_root = home / "repos" / "tw"
    _config_with(home, root=canonical_root)

    ws = workspace_factory()
    manifest = f'name = "{ws.name}"\n'

    for spec, branch, base in repos:
        forge, org, name = (
            spec.split("/") if spec.count("/") == 2 else ("github.com", *spec.split("/"))
        )
        canonical_target = canonical_root / forge / org / name
        canonical_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(canonical_factory(name)), str(canonical_target))
        worktree_factory(canonical_target, ws / name, branch=branch, base=base)
        manifest += f'\n[[repo]]\nrepo = "{spec}"\nbranch = "{branch}"\nbase = "{base}"\n'

    (ws / "brunch.toml").write_text(manifest, encoding="utf-8")
    return ws


class TestStatusE2E:
    def test_status_renders_workspace_with_repos(
        self,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        ws = _setup_workspace(
            home=isolated_home,
            canonical_factory=make_canonical,
            workspace_factory=make_workspace,
            worktree_factory=worktree_factory,
            repos=[("acme/api", "feat", "main"), ("acme/dashboard", "feat", "main")],
        )

        result = runner.invoke(app, ["status", "-w", str(ws)])
        assert result.exit_code == 0, result.output
        assert "workspace" in result.output
        assert "api" in result.output
        assert "dashboard" in result.output
        # Both worktrees on the declared branch → clean.
        assert "clean" in result.output

    def test_status_json_round_trip(
        self,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        ws = _setup_workspace(
            home=isolated_home,
            canonical_factory=make_canonical,
            workspace_factory=make_workspace,
            worktree_factory=worktree_factory,
            repos=[("acme/api", "feat", "main")],
        )

        result = runner.invoke(app, ["status", "-w", str(ws), "--json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["workspace_name"] == ws.name
        assert len(payload["repos"]) == 1
        assert payload["repos"][0]["short_name"] == "api"
        assert payload["repos"][0]["on_declared_branch"] is True

    def test_status_flags_drift(
        self,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        ws = _setup_workspace(
            home=isolated_home,
            canonical_factory=make_canonical,
            workspace_factory=make_workspace,
            worktree_factory=worktree_factory,
            repos=[("acme/api", "feat", "main")],
        )
        # Switch the worktree to a different branch.
        import subprocess

        subprocess.run(
            ["git", "checkout", "-b", "different"],
            cwd=ws / "api",
            check=True,
            capture_output=True,
        )

        result = runner.invoke(app, ["status", "-w", str(ws), "--json"])
        payload = json.loads(result.output)
        assert payload["repos"][0]["on_declared_branch"] is False
        assert payload["repos"][0]["current_branch"] == "different"

    def test_status_no_workspace_exits_3(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["status", "-w", str(tmp_path)])
        assert result.exit_code == 3
