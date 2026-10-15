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
    remote: str | None = typer.Option(
        None, "--remote", "-r", help="Remote to fetch and branch from (default: see below)."
    ),
    no_fetch: bool = typer.Option(
        False, "--no-fetch", help="Do not fetch; start from the local base branch."
    ),
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
    """Add a repo to the workspace and create its worktree.

    The repo must already be cloned under your brunch root, because brunch never
    clones. The worktree is created at `./<repo-name>` on `--branch` (default: the
    workspace name).

    First it fetches the repo's remote, then starts the new branch from the
    remote's copy of `--base` (default `main`), so the branch begins at the
    current tip rather than at a stale local `main`. The new branch does not track
    the remote branch. A base other than the remote's default branch starts from
    the local branch of that name when there is one. If the fetch fails, nothing is
    created; `--no-fetch` works offline by starting from the local base instead.

    The remote is `--remote`, else git's `checkout.defaultRemote`, else the only
    remote, else `origin`. A repo with no remotes skips the fetch.

    It refuses if the branch already exists in the clone (as `git checkout -b`
    does), including when it is checked out in another worktree. A branch left
    over from a removed workspace is the usual cause: pick another `--branch`, or
    delete the old one. It does not work at a set root.

    REPO is `org/repo` or `forge/org/repo`.

    Example:

    ```
    br add example/backend
    br add github.com/example/frontend --branch PROJECT-1234_frontend-only
    ```
    """

    location = discover_workspace(workspace or Path.cwd())
    cfg = load_config()
    outcome = add_repo(
        location,
        cfg,
        repo=repo,
        branch=branch,
        base=base,
        remote=remote,
        fetch=not no_fetch,
        dry_run=dry_run,
    )

    if json_output:
        typer.echo(outcome.model_dump_json(indent=2))
    else:
        render_add_outcome(outcome)
