"""Controller for ``brunch pull``."""

from __future__ import annotations

from pathlib import Path

import typer

from brunch.config import load_config
from brunch.paths import discover_workspace
from brunch.rendering import render_pull_report, render_set_pull_report
from brunch.services.pull import pull_workspace
from brunch.services.set_ops import pull_set


def pull(
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
    """Run `git pull` in every repo of the workspace.

    Updates each checked-out branch from its upstream, using your git pull
    settings. A branch with no upstream cannot be pulled, and that repo is
    reported as an error. This includes branches created by `br add`, until you
    push them with `git push -u`. Repos with no remote are skipped. At a set root
    it covers every workspace in the set. It exits 1 if any pull fails.

    Example:

    ```
    br pull --dry-run
    ```
    """

    location = discover_workspace(workspace or Path.cwd())
    cfg = load_config()

    if location.mode == "set":
        set_report = pull_set(location, cfg, dry_run=dry_run)
        if json_output:
            typer.echo(set_report.model_dump_json(indent=2))
        else:
            render_set_pull_report(set_report)
        if set_report.has_errors:
            raise typer.Exit(code=1)
        return

    report = pull_workspace(location, cfg, dry_run=dry_run)
    if json_output:
        typer.echo(report.model_dump_json(indent=2))
    else:
        render_pull_report(report)
    if report.has_errors:
        raise typer.Exit(code=1)
