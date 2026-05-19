from __future__ import annotations

import typer


def sync(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON records."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would happen."),
) -> None:
    """Reconcile on-disk worktrees with the manifest (non-destructive)."""
    typer.secho("brunch sync: not implemented yet (M2).", fg=typer.colors.YELLOW)
    raise typer.Exit(code=2)
