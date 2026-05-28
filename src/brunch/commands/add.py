"""Controller for ``brunch add``."""

from __future__ import annotations

from pathlib import Path

import typer

from brunch.config import load_config
from brunch.paths import discover_workspace
from brunch.rendering import render_add_outcome
from brunch.services.add import add_repo


def add(
    repo: str = typer.Argument(
        ..., help="Repo spec, e.g. 'kybernetix/api' or 'github.com/kybernetix/api'."
    ),
    branch: str | None = typer.Option(
        None, "--branch", help="Branch to check out (default: workspace name)."
    ),
    base: str = typer.Option("main", "--base", help="Branch to start from when creating."),
    workspace: Path | None = typer.Option(
        None,
        "-w",
        "--workspace",
        help="Operate on the workspace at this path (default: walk up from cwd).",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would happen without doing it."
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON instead of text."),
) -> None:
    """Add a repo to the current workspace and create its worktree."""

    location = discover_workspace(workspace or Path.cwd())
    cfg = load_config()
    outcome = add_repo(
        location,
        cfg,
        repo=repo,
        branch=branch,
        base=base,
        dry_run=dry_run,
    )

    if json_output:
        typer.echo(outcome.model_dump_json(indent=2))
    else:
        render_add_outcome(outcome)
