from __future__ import annotations

import typer


def rm(
    force: bool = typer.Option(
        False,
        "--force",
        help="Archive then remove even if dirty (uncommitted/unpushed).",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would happen."),
) -> None:
    """Remove the workspace; archive first if --force is required."""
    typer.secho("brunch rm: not implemented yet (M4).", fg=typer.colors.YELLOW)
    raise typer.Exit(code=2)
