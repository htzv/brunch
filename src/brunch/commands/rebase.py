from __future__ import annotations

import typer


def rebase(
    onto: str | None = typer.Option(None, "--onto", help="Override target branch."),
    continue_on_error: bool = typer.Option(
        False,
        "--continue-on-error",
        help="Continue rebasing remaining repos after a conflict.",
    ),
    autostash: bool = typer.Option(False, "--autostash", help="Pass --autostash to git rebase."),
    no_fetch: bool = typer.Option(False, "--no-fetch", help="Skip the pre-rebase fetch step."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would happen."),
) -> None:
    """Per-repo fetch + rebase onto base (or --onto). Stops on first conflict."""
    typer.secho("brunch rebase: not implemented yet (M3).", fg=typer.colors.YELLOW)
    raise typer.Exit(code=2)
