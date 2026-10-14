"""Controller for ``br drop`` — remove one repo's worktree from the workspace."""

from __future__ import annotations

from pathlib import Path

import typer

from brunch.config import load_config
from brunch.paths import discover_workspace
from brunch.rendering import render_drop_outcome
from brunch.services.drop import drop_repo


def drop(
    repo: str = typer.Argument(..., help="Repo to remove (short name or spec)."),
    force: bool = typer.Option(
        False, "--force", "-f", help="Drop even with uncommitted/untracked/unpushed work."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would happen; change nothing."
    ),
    workspace: Path | None = typer.Option(
        None, "-w", "--workspace", help="Operate on the workspace at this path (default: cwd)."
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON instead of a summary."),
) -> None:
    """Remove one repo's worktree and its `brunch.toml` entry.

    The rest of the workspace and the cloned repo are left alone, and the branch
    stays in the clone. It refuses if the worktree has uncommitted changes,
    untracked files, or commits that are not pushed. `--force` overrides that.
    REPO is the short name or the `org/repo` form.

    Example:

    ```
    br drop backend --dry-run
    ```
    """

    location = discover_workspace(workspace or Path.cwd())
    outcome = drop_repo(location, load_config(), repo, force=force, dry_run=dry_run)
    if json_output:
        typer.echo(outcome.model_dump_json(indent=2))
    else:
        render_drop_outcome(outcome)
    if outcome.action in ("refused", "error"):
        raise typer.Exit(code=1)
