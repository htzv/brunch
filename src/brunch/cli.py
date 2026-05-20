from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

import typer

from brunch import __version__
from brunch.commands import (
    add,
    adopt,
    fetch,
    foreach,
    fsck,
    init,
    pull,
    rebase,
    rm,
    status,
    sync,
)
from brunch.errors import BrunchError


def _handle_errors(handler: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap a controller so that BrunchError becomes a stderr message + exit code.

    ``functools.wraps`` preserves the original signature (via ``__wrapped__``),
    which Typer follows when introspecting parameters.
    """

    @functools.wraps(handler)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return handler(*args, **kwargs)
        except BrunchError as e:
            typer.secho(f"error: {e.message}", err=True, fg=typer.colors.RED)
            if e.hint:
                typer.secho(f"hint: {e.hint}", err=True, fg=typer.colors.BLUE)
            raise typer.Exit(code=e.exit_code) from e

    return wrapper


app = typer.Typer(
    name="brunch",
    help="Mise en place for git worktree-based multi-repo task workspaces.",
    no_args_is_help=True,
    add_completion=False,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"brunch {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show brunch version and exit.",
    ),
) -> None:
    """Mise en place for git worktree-based multi-repo task workspaces."""


# Register subcommands. Each module exposes a single function named after the
# command it implements; ``_handle_errors`` translates BrunchError into clean
# stderr output and stable exit codes.
app.command("init", help="Create a new workspace (or set with --set).")(_handle_errors(init.init))
app.command(
    "adopt",
    help="Retroactively bring an existing folder of worktrees under brunch.",
)(_handle_errors(adopt.adopt))
app.command("add", help="Add a repo to the current workspace; create its worktree.")(
    _handle_errors(add.add)
)
app.command("sync", help="Reconcile on-disk worktrees with the manifest.")(
    _handle_errors(sync.sync)
)
app.command("status", help="Summarised git status across all repos.")(_handle_errors(status.status))
app.command("fetch", help="Fan out `git fetch` across all repos.")(_handle_errors(fetch.fetch))
app.command("pull", help="Fan out `git pull` across all repos.")(_handle_errors(pull.pull))
app.command("rebase", help="Per-repo fetch + rebase onto base (or --onto).")(
    _handle_errors(rebase.rebase)
)
app.command("foreach", help="Run a command in each repo of the workspace.")(
    _handle_errors(foreach.foreach)
)
app.command("rm", help="Remove the workspace; archive first if --force.")(_handle_errors(rm.rm))
app.command("fsck", help="Diagnose workspace health; --fix runs safe remediations.")(
    _handle_errors(fsck.fsck)
)


if __name__ == "__main__":
    app()
