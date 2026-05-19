"""Controller for ``brunch fsck`` — thin renderer over the fsck service."""

from __future__ import annotations

from pathlib import Path

import typer

from brunch.config import load_config
from brunch.paths import discover_workspace
from brunch.rendering import render_fsck_report
from brunch.services.fsck import fsck_workspace


def fsck(
    workspace: Path | None = typer.Option(
        None,
        "-w",
        "--workspace",
        help="Operate on the workspace at this path (default: walk up from cwd).",
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON instead of text."),
    fix: bool = typer.Option(
        False, "--fix", help="Apply safe automatic remediations (parked for M5)."
    ),
) -> None:
    """Diagnose workspace health; with --fix, perform safe remediations."""

    if fix:
        typer.secho(
            "brunch fsck --fix: no fixable issues in M1 (gc lands in M5).",
            fg=typer.colors.YELLOW,
            err=True,
        )

    location = discover_workspace(workspace or Path.cwd())
    cfg = load_config()
    report = fsck_workspace(location, cfg)

    if json_output:
        typer.echo(report.model_dump_json(indent=2))
    else:
        render_fsck_report(report)

    if report.has_errors:
        raise typer.Exit(code=1)
