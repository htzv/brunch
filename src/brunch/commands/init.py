from __future__ import annotations

import typer


def init(
    name: str = typer.Argument(..., help="Name of the workspace (or set)."),
    template: str | None = typer.Option(
        None, "-t", "--template", help="Template id under ~/.config/brunch/templates/."
    ),
    set_mode: bool = typer.Option(
        False, "--set", help="Create a workspace set instead of a workspace."
    ),
) -> None:
    """Create a new workspace or workspace set."""
    typer.secho("brunch init: not implemented yet (M2).", fg=typer.colors.YELLOW)
    raise typer.Exit(code=2)
