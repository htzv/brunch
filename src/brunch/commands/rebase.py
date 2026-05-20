"""Controller for ``brunch rebase``."""

from __future__ import annotations

from pathlib import Path

import typer

from brunch.config import load_config
from brunch.paths import discover_workspace
from brunch.rendering import render_rebase_report
from brunch.services.rebase import rebase_workspace


def rebase(
    onto: str | None = typer.Option(None, "--onto", help="Override target branch."),
    continue_on_error: bool = typer.Option(
        False,
        "--continue-on-error",
        help="Continue rebasing remaining repos after a conflict.",
    ),
    autostash: bool = typer.Option(False, "--autostash", help="Pass --autostash to git rebase."),
    no_fetch: bool = typer.Option(False, "--no-fetch", help="Skip the pre-rebase fetch step."),
    workspace: Path | None = typer.Option(
        None,
        "-w",
        "--workspace",
        help="Operate on the workspace at this path (default: walk up from cwd).",
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON instead of text."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would happen without doing it."
    ),
) -> None:
    """Per-repo fetch + rebase onto base (or --onto). Stops on first conflict."""

    location = discover_workspace(workspace or Path.cwd())
    cfg = load_config()
    report = rebase_workspace(
        location,
        cfg,
        onto=onto,
        autostash=autostash,
        no_fetch=no_fetch,
        continue_on_error=continue_on_error,
        dry_run=dry_run,
    )

    if json_output:
        typer.echo(report.model_dump_json(indent=2))
    else:
        render_rebase_report(report)

    if report.has_errors or report.has_conflicts:
        raise typer.Exit(code=1)
