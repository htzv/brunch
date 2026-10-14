"""The help text comes from docstrings, and the exit-code table matches errors.py."""

from __future__ import annotations

import inspect

from typer.testing import CliRunner

from brunch import errors
from brunch.cli import agent_app, app

runner = CliRunner()
COLUMNS_WIDE_ENOUGH_TO_AVOID_WRAPPING = "200"


def _registered_commands() -> list:
    return [*app.registered_commands, *agent_app.registered_commands]


def _declared_exit_codes() -> set[int]:
    return {
        cls.exit_code
        for _, cls in inspect.getmembers(errors, inspect.isclass)
        if issubclass(cls, errors.BrunchError) and cls is not errors.BrunchError
    }


def test_commands_have_no_help_override_so_docstrings_are_the_help() -> None:
    assert [c.name for c in _registered_commands() if c.help is not None] == []


def test_every_command_has_a_docstring() -> None:
    missing = [c.name for c in _registered_commands() if not inspect.getdoc(c.callback)]
    assert missing == []


def _exit_codes_shown_in_help(output: str) -> set[int]:
    rows = (line.split() for line in output.splitlines() if line.startswith("  "))
    return {int(cells[0]) for cells in rows if cells and cells[0].isdigit()}


def test_top_level_help_lists_every_exit_code_in_errors_module() -> None:
    result = runner.invoke(app, ["--help"], env={"COLUMNS": COLUMNS_WIDE_ENOUGH_TO_AVOID_WRAPPING})
    assert _declared_exit_codes() <= _exit_codes_shown_in_help(result.output)
