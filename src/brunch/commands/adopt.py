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
    """Adopt an existing folder of worktrees as a brunch workspace."""

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
