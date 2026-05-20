"""Controller for ``brunch rm``."""

from __future__ import annotations

from pathlib import Path

import typer

from brunch.config import load_config
from brunch.paths import discover_workspace
from brunch.rendering import render_rm_outcome, render_set_rm_outcome
from brunch.services.rm import rm_workspace
from brunch.services.set_ops import rm_set


def rm(
    force: bool = typer.Option(
        False,
        "--force",
        help="Archive then remove even if any repo has at-risk content.",
    ),
    workspace: Path | None = typer.Option(
        None,
        "-w",
        "--workspace",
        help="Operate on the workspace (or set) at this path (default: walk up from cwd).",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would happen without doing it."
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON instead of text."),
) -> None:
    """Remove the workspace (or set); archive first if --force."""

    location = discover_workspace(workspace or Path.cwd())
    cfg = load_config()

    if location.mode == "set":
        set_outcome = rm_set(location, cfg, force=force, dry_run=dry_run)
        if json_output:
            typer.echo(set_outcome.model_dump_json(indent=2))
        else:
            render_set_rm_outcome(set_outcome)
        if set_outcome.action in ("refused", "error"):
            raise typer.Exit(code=1)
        return

    outcome = rm_workspace(location, cfg, force=force, dry_run=dry_run)
    if json_output:
        typer.echo(outcome.model_dump_json(indent=2))
    else:
        render_rm_outcome(outcome)
    if outcome.action in ("refused", "error"):
        raise typer.Exit(code=1)
