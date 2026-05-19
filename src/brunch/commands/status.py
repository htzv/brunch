from __future__ import annotations

import typer


def status(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON records."),
) -> None:
    """Summarised git status across all repos in the workspace."""
    typer.secho("brunch status: not implemented yet (M1).", fg=typer.colors.YELLOW)
    raise typer.Exit(code=2)
