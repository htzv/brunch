"""Fixtures shared by the end-to-end tests that need a real origin."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from brunch.cli import app
from tests.conftest import OriginRepo

_runner = CliRunner()
MakeOrigin = Callable[..., OriginRepo]


@pytest.fixture
def stale_setup(
    tmp_path: Path, isolated_home: Path, make_origin: MakeOrigin
) -> tuple[OriginRepo, Path, str]:
    """A canonical whose local main is behind origin, and an empty workspace.

    Returns the origin, the workspace path, and origin's new tip.
    """

    origin = make_origin("api")
    new_tip = origin.advance()
    canonical_root = tmp_path / "canonical-root"
    target = canonical_root / "github.com" / "kybernetix" / "api"
    target.parent.mkdir(parents=True)
    shutil.move(str(origin.canonical), str(target))
    origin.canonical = target
    config_dir = isolated_home / ".config" / "brunch"
    config_dir.mkdir(parents=True)
    (config_dir / "config.toml").write_text(f'root = "{canonical_root}"\n', encoding="utf-8")
    result = _runner.invoke(app, ["init", "task-1", "-p", str(isolated_home)])
    assert result.exit_code == 0, result.output
    return origin, isolated_home / "task-1", new_tip
