from __future__ import annotations

import typer


def add(
    repo: str = typer.Argument(..., help="Repo spec, e.g. github.com/acme/api or acme/api."),
    branch: str | None = typer.Option(
        None, "--branch", help="Branch to check out in the worktree."
    ),
    base: str | None = typer.Option(None, "--base", help="Branch to start from if creating."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would happen."),
) -> None:
    """Add a repo to the current workspace and create its worktree."""
    typer.secho("brunch add: not implemented yet (M2).", fg=typer.colors.YELLOW)
    raise typer.Exit(code=2)
