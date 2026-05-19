from __future__ import annotations

import typer

from brunch import __version__
from brunch.commands import (
    add,
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
# command it implements; binding them here keeps the file shape uniform.
app.command("init", help="Create a new workspace (or set with --set).")(init.init)
app.command("add", help="Add a repo to the current workspace; create its worktree.")(add.add)
app.command("sync", help="Reconcile on-disk worktrees with the manifest.")(sync.sync)
app.command("status", help="Summarised git status across all repos.")(status.status)
app.command("fetch", help="Fan out `git fetch` across all repos.")(fetch.fetch)
app.command("pull", help="Fan out `git pull` across all repos.")(pull.pull)
app.command("rebase", help="Per-repo fetch + rebase onto base (or --onto).")(rebase.rebase)
app.command("foreach", help="Run a command in each repo of the workspace.")(foreach.foreach)
app.command("rm", help="Remove the workspace; archive first if --force.")(rm.rm)
app.command("fsck", help="Diagnose workspace health; --fix runs safe remediations.")(fsck.fsck)


if __name__ == "__main__":
    app()
