"""Controller for ``brunch sync``."""

from __future__ import annotations

from pathlib import Path

import typer

from brunch.config import load_config
from brunch.paths import discover_workspace
from brunch.rendering import render_sync_report
from brunch.services.sync import sync_workspace


def sync(
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
    """Reconcile on-disk worktrees with the manifest (non-destructive)."""

    location = discover_workspace(workspace or Path.cwd())
    cfg = load_config()
    report = sync_workspace(location, cfg, dry_run=dry_run)

    if json_output:
        typer.echo(report.model_dump_json(indent=2))
    else:
        render_sync_report(report)

    if report.has_errors:
        raise typer.Exit(code=1)
