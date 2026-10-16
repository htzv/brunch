"""`br add` starts from the remote's default branch when `--base` is not given."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from typer.testing import CliRunner

from brunch.cli import app
from tests.conftest import OriginRepo, _git

runner = CliRunner()
SetupFor = Callable[[str], tuple[OriginRepo, Path, str]]


def _add(ws: Path, *extra: str) -> tuple[int, str]:
    result = runner.invoke(app, ["add", "kybernetix/api", "-w", str(ws), *extra])
    return result.exit_code, result.output


def test_a_repo_whose_default_branch_is_master_just_works(
    setup_with_default_branch: SetupFor,
) -> None:
    _, ws, new_tip = setup_with_default_branch("master")

    code, output = _add(ws, "--json")

    assert code == 0, output
    payload = json.loads(output)
    assert payload["base"] == "master"
    assert payload["start_point"] == "origin/master"
    assert _git(["rev-parse", "HEAD"], cwd=ws / "api").strip() == new_tip
    assert 'base = "master"' in (ws / "brunch.toml").read_text(encoding="utf-8")


def test_the_default_can_be_any_name(setup_with_default_branch: SetupFor) -> None:
    _, ws, _ = setup_with_default_branch("develop")
    _, output = _add(ws, "--json")
    assert json.loads(output)["base"] == "develop"


def test_an_explicit_base_still_wins(setup_with_default_branch: SetupFor) -> None:
    origin, ws, _ = setup_with_default_branch("master")
    origin.publish_branch("release", from_ref="master")

    code, output = _add(ws, "--base", "release", "--json")

    assert code == 0, output
    assert json.loads(output)["base"] == "release"


def test_no_fetch_uses_the_remote_head_already_there(
    setup_with_default_branch: SetupFor,
) -> None:
    origin, ws, _ = setup_with_default_branch("master")
    local_master = _git(["rev-parse", "master"], cwd=origin.canonical).strip()

    code, output = _add(ws, "--no-fetch", "--json")

    assert code == 0, output
    payload = json.loads(output)
    assert payload["base"] == "master"
    assert payload["start_point"] == "master"
    assert _git(["rev-parse", "HEAD"], cwd=ws / "api").strip() == local_master


def test_without_a_remote_head_the_default_is_main(setup_with_default_branch: SetupFor) -> None:
    origin, ws, _ = setup_with_default_branch("main")
    _git(["remote", "set-head", "origin", "--delete"], cwd=origin.canonical)

    _, output = _add(ws, "--json")

    assert json.loads(output)["base"] == "main"


def test_a_repo_without_remotes_defaults_to_main(
    tmp_path: Path, isolated_home: Path, make_canonical: Callable[..., Path]
) -> None:
    import shutil

    root = tmp_path / "canonical-root"
    target = root / "github.com" / "kybernetix" / "api"
    target.parent.mkdir(parents=True)
    shutil.move(str(make_canonical("api")), str(target))
    config_dir = isolated_home / ".config" / "brunch"
    config_dir.mkdir(parents=True)
    (config_dir / "config.toml").write_text(f'root = "{root}"\n', encoding="utf-8")
    runner.invoke(app, ["init", "task-1", "-p", str(isolated_home)])

    _, output = _add(isolated_home / "task-1", "--json")

    assert json.loads(output)["base"] == "main"
