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
    no_fetch: bool = typer.Option(
        False, "--no-fetch", help="Do not fetch first; judge by the remote branches already here."
    ),
) -> None:
    """Remove the workspace: delete its worktrees, then the workspace directory.

    Refuses, and removes nothing, if any worktree has uncommitted changes,
    untracked files, or commits that are on no remote branch (unless the base
    branch already has their content after a rebase or squash merge, which the
    output then says). To know that
    reliably it first fetches every remote of each repo and prunes the remote
    branches that were deleted there. If a fetch fails (offline), it warns and
    judges by the remote branches from the last fetch, as git does;
    `--no-fetch` skips the attempt. `--force` removes anyway,
    after saving a tarball of the whole workspace in the `archives` folder of
    brunch's data directory.

    Only the worktrees listed in `brunch.toml` are deleted, and the branches stay
    in the cloned repos. Any other file or folder in the workspace is kept. When
    something is kept, `brunch.toml` stays too, without the repos whose
    worktrees were removed, so the directory remains an empty workspace. When
    nothing else is left, the directory is removed.

    At a set root it removes every workspace in the set, and refuses if any
    member refuses. Run it with `--dry-run` first.

    Example:

    ```
    br rm --dry-run
    ```
    """

    location = discover_workspace(workspace or Path.cwd())
    cfg = load_config()

    if location.mode == "set":
        set_outcome = rm_set(location, cfg, force=force, dry_run=dry_run, fetch=not no_fetch)
        if json_output:
            typer.echo(set_outcome.model_dump_json(indent=2))
        else:
            render_set_rm_outcome(set_outcome)
        if set_outcome.action in ("refused", "error"):
            raise typer.Exit(code=1)
        return

    outcome = rm_workspace(location, cfg, force=force, dry_run=dry_run, fetch=not no_fetch)
    if json_output:
        typer.echo(outcome.model_dump_json(indent=2))
    else:
        render_rm_outcome(outcome)
    if outcome.action in ("refused", "error"):
        raise typer.Exit(code=1)
