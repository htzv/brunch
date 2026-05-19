"""Controller for ``brunch init``."""

from __future__ import annotations

from pathlib import Path

import typer

from brunch.config import load_config
from brunch.rendering import render_init_outcome
from brunch.services.init import init_set, init_workspace


def init(
    name: str = typer.Argument(..., help="Name of the workspace (or set)."),
    template: str | None = typer.Option(
        None, "-t", "--template", help="Template id under ~/.config/brunch/templates/."
    ),
    set_mode: bool = typer.Option(
        False, "--set", help="Create a workspace set instead of a workspace."
    ),
    parent: Path | None = typer.Option(
        None,
        "-p",
        "--parent",
        help="Parent directory under which to create (default: cwd).",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would happen without doing it."
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON instead of text."),
) -> None:
    """Create a new workspace or workspace set."""

    target = (parent or Path.cwd()) / name
    cfg = load_config()

    if set_mode:
        outcome = init_set(target, name=name, dry_run=dry_run)
    else:
        outcome = init_workspace(
            target,
            name=name,
            config=cfg,
            template_id=template,
            dry_run=dry_run,
        )

    if json_output:
        typer.echo(outcome.model_dump_json(indent=2))
    else:
        render_init_outcome(outcome)

    if outcome.sync_report is not None and outcome.sync_report.has_errors:
        raise typer.Exit(code=1)
