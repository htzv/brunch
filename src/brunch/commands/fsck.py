from __future__ import annotations

import typer


def fsck(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON records."),
    fix: bool = typer.Option(
        False, "--fix", help="Perform safe automatic remediations (e.g. worktree prune)."
    ),
) -> None:
    """Diagnose workspace health; with --fix, perform safe remediations."""
    typer.secho("brunch fsck: not implemented yet (M1).", fg=typer.colors.YELLOW)
    raise typer.Exit(code=2)
