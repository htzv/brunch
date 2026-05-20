"""Controller for ``brunch status`` — thin renderer over the status service."""

from __future__ import annotations

from pathlib import Path

import typer

from brunch.config import load_config
from brunch.paths import discover_workspace
from brunch.rendering import render_set_status, render_workspace_status
from brunch.services.set_ops import compute_set_status
from brunch.services.status import compute_workspace_status


def status(
    workspace: Path | None = typer.Option(
        None,
        "-w",
        "--workspace",
        help="Operate on the workspace (or set) at this path (default: walk up from cwd).",
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON instead of a table."),
) -> None:
    """Summarised git status across all repos."""

    location = discover_workspace(workspace or Path.cwd())
    cfg = load_config()
    if location.mode == "set":
        report = compute_set_status(location, cfg)
        if json_output:
            typer.echo(report.model_dump_json(indent=2))
        else:
            render_set_status(report)
        return
    result = compute_workspace_status(location, cfg)
    if json_output:
        typer.echo(result.model_dump_json(indent=2))
    else:
        render_workspace_status(result)
