from __future__ import annotations

import typer


def foreach(
    command: list[str] = typer.Argument(
        ..., help="Command to run in each repo (use -- to separate)."
    ),
) -> None:
    """Run a command in each repo of the workspace."""
    typer.secho("brunch foreach: not implemented yet (M3).", fg=typer.colors.YELLOW)
    raise typer.Exit(code=2)
