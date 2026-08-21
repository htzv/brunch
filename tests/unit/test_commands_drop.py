"""CLI-level tests for `br drop`.

Exercise the controller wiring (discover → drop_repo → render/JSON → exit code)
that the service tests in ``test_services_drop.py`` don't reach. Real git in
temp dirs; ``load_config`` is patched so the canonical root points at the temp
ghq-style tree instead of the developer's real one.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

from typer.testing import CliRunner

from brunch.cli import app
from brunch.models import ToolConfig

runner = CliRunner()


def _install_canonical(
    make_canonical: Callable[..., Path], canonical_root: Path, *, name: str
) -> Path:
    target = canonical_root / "github.com" / "kybernetix" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(make_canonical(name)), str(target))
    return target


def _write_manifest(ws: Path, *, repos: list[tuple[str, str, str]]) -> None:
    text = f'name = "{ws.name}"\n'
    for repo, branch, base in repos:
        text += f'\n[[repo]]\nrepo = "{repo}"\nbranch = "{branch}"\nbase = "{base}"\n'
    (ws / "brunch.toml").write_text(text, encoding="utf-8")


def _patch_config(monkeypatch, root: Path) -> None:
    monkeypatch.setattr(
        "brunch.commands.drop.load_config",
        lambda: ToolConfig(root=root, default_forge="github.com"),
    )


def _setup(tmp_path, make_canonical, make_workspace, worktree_factory, monkeypatch):
    root = tmp_path / "canonical-root"
    api = _install_canonical(make_canonical, root, name="api")
    ws = make_workspace()
    worktree_factory(api, ws / "api", branch="feat", base="main")
    _write_manifest(ws, repos=[("kybernetix/api", "feat", "main")])
    _patch_config(monkeypatch, root)
    return ws, api


def test_drop_success_exits_zero_and_removes(
    tmp_path, make_canonical, make_workspace, worktree_factory, monkeypatch
):
    ws, _api = _setup(tmp_path, make_canonical, make_workspace, worktree_factory, monkeypatch)
    result = runner.invoke(app, ["drop", "api", "-w", str(ws)])
    assert result.exit_code == 0, result.output
    assert not (ws / "api").exists()


def test_drop_json_output(tmp_path, make_canonical, make_workspace, worktree_factory, monkeypatch):
    ws, _api = _setup(tmp_path, make_canonical, make_workspace, worktree_factory, monkeypatch)
    result = runner.invoke(app, ["drop", "api", "-w", str(ws), "--json"])
    assert result.exit_code == 0, result.output
    assert '"action": "dropped"' in result.output


def test_drop_dry_run_keeps_worktree(
    tmp_path, make_canonical, make_workspace, worktree_factory, monkeypatch
):
    ws, _api = _setup(tmp_path, make_canonical, make_workspace, worktree_factory, monkeypatch)
    result = runner.invoke(app, ["drop", "api", "-w", str(ws), "--dry-run"])
    assert result.exit_code == 0, result.output
    assert (ws / "api").exists()


def test_drop_refused_dirty_exits_one(
    tmp_path, make_canonical, make_workspace, worktree_factory, monkeypatch
):
    ws, _api = _setup(tmp_path, make_canonical, make_workspace, worktree_factory, monkeypatch)
    (ws / "api" / "dirty.txt").write_text("x\n", encoding="utf-8")  # untracked → at risk
    result = runner.invoke(app, ["drop", "api", "-w", str(ws)])
    assert result.exit_code == 1, result.output
    assert (ws / "api").exists()  # nothing removed


def test_drop_unknown_repo_errors(
    tmp_path, make_canonical, make_workspace, worktree_factory, monkeypatch
):
    ws, _api = _setup(tmp_path, make_canonical, make_workspace, worktree_factory, monkeypatch)
    result = runner.invoke(app, ["drop", "nope", "-w", str(ws)])
    assert result.exit_code != 0
    assert "not in this workspace" in result.output
