"""Smoke tests: the CLI is wired up and exposes the expected surface.

Per-command behaviour lives in tests/e2e/; this file only checks the top-level
plumbing and the stub-vs-implemented split.
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from brunch import __version__
from brunch.cli import app

runner = CliRunner()


STUB_COMMANDS = [
    ("init", ["x"]),
    ("add", ["acme/api"]),
    ("sync", []),
    ("fetch", []),
    ("pull", []),
    ("rebase", []),
    ("foreach", ["echo", "hi"]),
    ("rm", []),
]


def test_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_help_lists_all_v1_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    expected = {
        "init",
        "add",
        "sync",
        "status",
        "fetch",
        "pull",
        "rebase",
        "foreach",
        "rm",
        "fsck",
    }
    missing = expected - set(result.stdout.split())
    assert not missing, f"missing commands in --help: {missing}"


def test_stub_commands_exit_2() -> None:
    # Commands whose milestones haven't shipped yet exit with code 2
    # ("not implemented") so accidentally-empty bodies can't slip through.
    for cmd, args in STUB_COMMANDS:
        result = runner.invoke(app, [cmd, *args])
        assert result.exit_code == 2, f"{cmd}: expected exit 2, got {result.exit_code}"
        assert "not implemented" in result.stdout.lower(), f"{cmd}: stub message missing"


def test_implemented_commands_fail_cleanly_outside_a_workspace(tmp_path: Path) -> None:
    # status and fsck have real implementations (M1). Outside a workspace
    # they raise WorkspaceNotFoundError, which the global error handler
    # converts to exit code 3.
    for cmd in ["status", "fsck"]:
        result = runner.invoke(app, [cmd, "-w", str(tmp_path)])
        assert result.exit_code == 3, f"{cmd}: expected exit 3, got {result.exit_code}"
