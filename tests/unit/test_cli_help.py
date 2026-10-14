"""The help text comes from docstrings, and the exit-code table matches errors.py."""

from __future__ import annotations

import inspect
import re

from typer.testing import CliRunner

from brunch import errors
from brunch.cli import agent_app, app, main

runner = CliRunner()
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")
FIRST_EXAMPLE_LINE = "br init PROJECT-1234_add-export"


def _registered_commands() -> list:
    return [*app.registered_commands, *agent_app.registered_commands]


def _declared_exit_codes() -> set[int]:
    return {
        cls.exit_code
        for _, cls in inspect.getmembers(errors, inspect.isclass)
        if issubclass(cls, errors.BrunchError) and cls is not errors.BrunchError
    }


def _exit_codes_in_table(markdown: str) -> set[int]:
    rows = (line.strip("| ").split("|")[0].strip() for line in markdown.splitlines())
    return {int(cell) for cell in rows if cell.isdigit()}


def test_commands_have_no_help_override_so_docstrings_are_the_help() -> None:
    assert [c.name for c in _registered_commands() if c.help is not None] == []


def test_every_command_has_a_docstring() -> None:
    missing = [c.name for c in _registered_commands() if not inspect.getdoc(c.callback)]
    assert missing == []


def test_top_level_help_lists_every_exit_code_in_errors_module() -> None:
    assert _declared_exit_codes() <= _exit_codes_in_table(inspect.getdoc(main) or "")


def _example_commands(doc: str) -> list[str]:
    return [
        line.split()[1]
        for line in doc.splitlines()
        if line.startswith("br ") and len(line.split()) > 1
    ]


def test_top_level_example_only_uses_real_commands() -> None:
    commands = {c.name for c in app.registered_commands}
    used = _example_commands(inspect.getdoc(main) or "")
    assert used, "the top-level help should contain an example"
    assert set(used) <= commands


def test_rendered_top_level_help_shows_the_example() -> None:
    result = runner.invoke(app, ["--help"])
    assert FIRST_EXAMPLE_LINE in ANSI_ESCAPE.sub("", result.output)
