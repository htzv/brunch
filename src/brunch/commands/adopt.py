"""Controller for ``brunch adopt`` — retroactively bring an existing folder
of worktrees under brunch."""

from __future__ import annotations

from pathlib import Path

import typer

from brunch.config import load_config
from brunch.rendering import render_adopt_outcome
from brunch.services.adopt import adopt_workspace


def adopt(
    path: Path | None = typer.Argument(
        None,
        help="Directory to adopt (default: cwd).",
    ),
    name: str | None = typer.Option(
        None,
        "--name",
        help="Workspace name (default: target directory name).",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would happen without writing brunch.toml."
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON instead of text."),
) -> None:
    """Turn a folder of hand-made worktrees into a brunch workspace.

    Use it when you already created the worktrees with `git worktree add`. Brunch
    reads each worktree's repo and branch, writes `brunch.toml`, then runs
    `br sync` and `br fsck` to check the result. The worktrees are not moved or
    changed, and folders that are not git repos are left alone. If any worktree
    cannot be read, nothing is written.

    It records `base = "main"` for every repo, because the real starting branch
    cannot be worked out. Edit `brunch.toml` where a branch started elsewhere.

    Example:

    ```
    br adopt ~/work/PROJECT-1234_add-export
    ```
    """

    target = (path or Path.cwd()).resolve()
    effective_name = name or target.name
    cfg = load_config()

    outcome = adopt_workspace(
        target,
        name=effective_name,
        config=cfg,
        dry_run=dry_run,
    )

    if json_output:
        typer.echo(outcome.model_dump_json(indent=2))
    else:
        render_adopt_outcome(outcome)

    if outcome.action == "failed":
        raise typer.Exit(code=1)
