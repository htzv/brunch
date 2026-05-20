"""Controller for ``brunch pull``."""

from __future__ import annotations

from pathlib import Path

import typer

from brunch.config import load_config
from brunch.paths import discover_workspace
from brunch.rendering import render_pull_report
from brunch.services.pull import pull_workspace


def pull(
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
    """Fan out `git pull` across all repos in the workspace."""

    location = discover_workspace(workspace or Path.cwd())
    cfg = load_config()
    report = pull_workspace(location, cfg, dry_run=dry_run)

    if json_output:
        typer.echo(report.model_dump_json(indent=2))
    else:
        render_pull_report(report)

    if report.has_errors:
        raise typer.Exit(code=1)
