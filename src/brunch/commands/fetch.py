"""Controller for ``brunch fetch``."""

from __future__ import annotations

from pathlib import Path

import typer

from brunch.config import load_config
from brunch.paths import discover_workspace
from brunch.rendering import render_fetch_report, render_set_fetch_report
from brunch.services.fetch import fetch_workspace
from brunch.services.set_ops import fetch_set


def fetch(
    workspace: Path | None = typer.Option(
        None,
        "-w",
        "--workspace",
        help="Operate on the workspace (or set) at this path (default: walk up from cwd).",
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON instead of text."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would happen without doing it."
    ),
) -> None:
    """Fan out `git fetch` across all repos in the workspace (or set)."""

    location = discover_workspace(workspace or Path.cwd())
    cfg = load_config()

    if location.mode == "set":
        set_report = fetch_set(location, cfg, dry_run=dry_run)
        if json_output:
            typer.echo(set_report.model_dump_json(indent=2))
        else:
            render_set_fetch_report(set_report)
        if set_report.has_errors:
            raise typer.Exit(code=1)
        return

    report = fetch_workspace(location, cfg, dry_run=dry_run)
    if json_output:
        typer.echo(report.model_dump_json(indent=2))
    else:
        render_fetch_report(report)
    if report.has_errors:
        raise typer.Exit(code=1)
