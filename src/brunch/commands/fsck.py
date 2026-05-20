"""Controller for ``brunch fsck`` — thin renderer over the fsck service."""

from __future__ import annotations

from pathlib import Path

import typer

from brunch.config import load_config
from brunch.paths import discover_workspace
from brunch.rendering import render_fsck_report, render_set_fsck_report
from brunch.services.fsck import fsck_workspace
from brunch.services.set_ops import fsck_set


def fsck(
    workspace: Path | None = typer.Option(
        None,
        "-w",
        "--workspace",
        help="Operate on the workspace (or set) at this path (default: walk up from cwd).",
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON instead of text."),
    fix: bool = typer.Option(
        False, "--fix", help="Apply safe automatic remediations (parked for M5+)."
    ),
) -> None:
    """Diagnose workspace (or set) health; with --fix, perform safe remediations."""

    if fix:
        typer.secho(
            "brunch fsck --fix: no fixable issues in this milestone (gc lands later).",
            fg=typer.colors.YELLOW,
            err=True,
        )

    location = discover_workspace(workspace or Path.cwd())
    cfg = load_config()

    if location.mode == "set":
        set_report = fsck_set(location, cfg)
        if json_output:
            typer.echo(set_report.model_dump_json(indent=2))
        else:
            render_set_fsck_report(set_report)
        if set_report.has_errors:
            raise typer.Exit(code=1)
        return

    report = fsck_workspace(location, cfg)
    if json_output:
        typer.echo(report.model_dump_json(indent=2))
    else:
        render_fsck_report(report)
    if report.has_errors:
        raise typer.Exit(code=1)
