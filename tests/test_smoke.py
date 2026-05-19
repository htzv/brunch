"""M0 smoke tests: the CLI is wired up and exposes the expected surface."""

from __future__ import annotations

from typer.testing import CliRunner

from brunch import __version__
from brunch.cli import app

runner = CliRunner()


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


def test_each_command_stub_exits_non_zero() -> None:
    # Stubs should exit with code 2 ("not implemented yet") until their
    # milestone lands. This guards against accidentally shipping a stub
    # that silently exits 0.
    for cmd, args in [
        ("init", ["x"]),
        ("add", ["acme/api"]),
        ("sync", []),
        ("status", []),
        ("fetch", []),
        ("pull", []),
        ("rebase", []),
        ("foreach", ["echo", "hi"]),
        ("rm", []),
        ("fsck", []),
    ]:
        result = runner.invoke(app, [cmd, *args])
        assert result.exit_code == 2, f"{cmd}: expected exit 2, got {result.exit_code}"
        assert "not implemented" in result.stdout.lower(), f"{cmd}: stub message missing"
