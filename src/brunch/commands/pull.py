from __future__ import annotations

import typer


def pull(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would happen."),
) -> None:
    """Fan out `git pull` across all repos in the workspace."""
    typer.secho("brunch pull: not implemented yet (M3).", fg=typer.colors.YELLOW)
    raise typer.Exit(code=2)
