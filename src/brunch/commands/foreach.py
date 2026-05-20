"""Controller for ``brunch foreach``."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from brunch.config import load_config
from brunch.paths import discover_workspace
from brunch.rendering import render_foreach_report, render_set_foreach_report
from brunch.services.foreach import foreach_workspace
from brunch.services.set_ops import foreach_set


def foreach(
    command: list[str] = typer.Argument(
        ..., help="Command to run in each repo (use -- to separate)."
    ),
    workspace: Path | None = typer.Option(
        None,
        "-w",
        "--workspace",
        help="Operate on the workspace (or set) at this path (default: walk up from cwd).",
    ),
    continue_on_error: bool = typer.Option(
        False,
        "--continue-on-error",
        help="Continue running remaining repos after a failure.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Capture output per-repo and emit JSON instead of streaming.",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would happen without doing it."
    ),
) -> None:
    """Run a command in each repo of the workspace (or set)."""

    location = discover_workspace(workspace or Path.cwd())
    cfg = load_config()
    console = Console()

    def _header(short_name: str, worktree_path: Path) -> None:
        console.print(f"\n[bold cyan]==> {short_name}[/bold cyan]  [dim]({worktree_path})[/dim]")

    if location.mode == "set":
        set_report = foreach_set(
            location,
            cfg,
            command=list(command),
            capture_output=json_output,
            continue_on_error=continue_on_error,
            dry_run=dry_run,
        )
        if json_output:
            typer.echo(set_report.model_dump_json(indent=2))
        else:
            console.print()
            render_set_foreach_report(set_report, console=console)
        if set_report.has_errors:
            raise typer.Exit(code=1)
        return

    report = foreach_workspace(
        location,
        cfg,
        command=list(command),
        capture_output=json_output,
        continue_on_error=continue_on_error,
        dry_run=dry_run,
        header=None if json_output or dry_run else _header,
    )

    if json_output:
        typer.echo(report.model_dump_json(indent=2))
    else:
        console.print()
        render_foreach_report(report, console=console)

    if report.has_errors:
        raise typer.Exit(code=1)
