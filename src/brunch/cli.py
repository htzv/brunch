from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

import typer

from brunch import __version__, experimental
from brunch.commands import (
    add,
    adopt,
    agent,
    drop,
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
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="markdown",
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
    enable_experimental: str | None = typer.Option(
        None,
        "--enable-experimental",
        metavar="FEATURE[,FEATURE…]",
        help=(
            "Opt into experimental, possibly-dangerous features (e.g. 'agent-rm'). Comma-separated."
        ),
    ),
) -> None:
    """Mise en place for git worktree-based multi-repo task workspaces.

    A workspace is a directory with one git worktree per repo, for one task. By
    default every worktree is on a branch named after the workspace. A typical
    session:

    ```
    br init PROJECT-1234_add-export        # new workspace directory
    cd PROJECT-1234_add-export
    br add example/backend                 # worktree ./backend
    br add github.com/example/frontend     # worktree ./frontend
    br status                              # one table for all repos
    br rm                                  # remove the workspace when done
    ```

    The repos must already be cloned under your brunch root, because brunch never
    clones. Run `br <command> --help` for what a command does and which flags it
    takes.

    Exit codes:

    | Code | Meaning |
    |---|---|
    | 0 | Success |
    | 1 | Refused or failed, for example `rm` found work at risk |
    | 2 | Usage error, or an experimental feature used without opting in |
    | 3 | No workspace found |
    | 4 | Invalid `brunch.toml` |
    | 5 | Invalid tool config |
    | 6 | Invalid repo spec |
    | 7 | A git command failed |
    | 8 | Template error |
    | 9 | Target already exists |
    | 10 | Branch is already checked out elsewhere |
    | 11 | Repo is already in the workspace |
    | 12 | Agent error |
    """
    try:
        experimental.set_enabled(enable_experimental)
    except BrunchError as e:
        typer.secho(f"error: {e.message}", err=True, fg=typer.colors.RED)
        if e.hint:
            typer.secho(f"hint: {e.hint}", err=True, fg=typer.colors.BLUE)
        raise typer.Exit(code=e.exit_code) from e


# Register subcommands. Each module exposes a single function named after the
# command it implements. Its docstring is the command's help text.
# ``_handle_errors`` translates BrunchError into clean stderr output and stable
# exit codes.
app.command("init")(_handle_errors(init.init))
app.command("adopt")(_handle_errors(adopt.adopt))
app.command("add")(_handle_errors(add.add))
app.command("sync")(_handle_errors(sync.sync))
app.command("status")(_handle_errors(status.status))
app.command("fetch")(_handle_errors(fetch.fetch))
app.command("pull")(_handle_errors(pull.pull))
app.command("rebase")(_handle_errors(rebase.rebase))
app.command("foreach")(_handle_errors(foreach.foreach))
app.command("rm")(_handle_errors(rm.rm))
app.command("drop")(_handle_errors(drop.drop))
app.command("fsck")(_handle_errors(fsck.fsck))

# `br agent …` — coding-agent conversation registry (Claude Code / OpenCode).
agent_app = typer.Typer(
    name="agent",
    help="Start, list, resume, and reconcile coding-agent conversations for this workspace.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="markdown",
)
agent_app.command("new")(_handle_errors(agent.agent_new))
agent_app.command("list")(_handle_errors(agent.agent_list))
agent_app.command("resume")(_handle_errors(agent.agent_resume))
agent_app.command("register")(_handle_errors(agent.agent_register))
agent_app.command("sync")(_handle_errors(agent.agent_sync))
agent_app.command("rm")(_handle_errors(agent.agent_rm))
app.add_typer(agent_app)


if __name__ == "__main__":
    app()
