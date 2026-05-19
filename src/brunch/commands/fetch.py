from __future__ import annotations

import typer


def fetch(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would happen."),
) -> None:
    """Fan out `git fetch` across all repos in the workspace."""
    typer.secho("brunch fetch: not implemented yet (M3).", fg=typer.colors.YELLOW)
    raise typer.Exit(code=2)
