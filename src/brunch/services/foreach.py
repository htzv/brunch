"""Service: run a shell command in each repo of a workspace.

Two modes:

- ``capture_output=False`` (default for the human CLI): subprocess inherits
  stdout/stderr so the user sees output live; the report contains only exit
  codes and an aggregated status.
- ``capture_output=True`` (for ``--json``): output is captured and embedded
  in each :class:`ForeachAction`.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

from brunch.errors import RepoSpecError, WorkspaceNotFoundError
from brunch.manifest import load_workspace_manifest
from brunch.models import (
    ForeachAction,
    ForeachActionType,
    ForeachReport,
    RepoEntry,
    ToolConfig,
    WorkspaceLocation,
)
from brunch.paths import parse_repo_spec


def foreach_workspace(
    location: WorkspaceLocation,
    config: ToolConfig,
    *,
    command: list[str],
    capture_output: bool = False,
    continue_on_error: bool = False,
    dry_run: bool = False,
    header: Callable[[str, Path], None] | None = None,
) -> ForeachReport:
    """Run ``command`` in every worktree.

    ``header`` is an optional callback invoked before each repo runs; useful
    for the streaming CLI mode to print a separator without coupling the
    service to a particular renderer.
    """

    if location.mode != "workspace":
        raise WorkspaceNotFoundError(
            f"foreach at set roots isn't supported yet (got mode={location.mode!r})",
            hint="cd into one of the child workspaces, or pass -w <path>.",
        )

    if not command:
        raise WorkspaceNotFoundError("foreach requires a command to run")

    manifest = load_workspace_manifest(location.manifest_path)
    actions: list[ForeachAction] = []
    stop = False

    for entry in manifest.repos:
        if stop:
            actions.append(
                ForeachAction(
                    repo=entry.repo,
                    short_name=entry.repo.split("/")[-1],
                    action="skipped",
                    message="skipped after earlier failure (use --continue-on-error)",
                )
            )
            continue

        action = _foreach_one(
            entry,
            location.root,
            config,
            command=command,
            capture_output=capture_output,
            dry_run=dry_run,
            header=header,
        )
        actions.append(action)
        if action.action in ("failed", "error") and not continue_on_error:
            stop = True

    return ForeachReport(
        workspace_name=manifest.name,
        workspace_path=location.root,
        command=command,
        actions=actions,
        dry_run=dry_run,
    )


def _foreach_one(
    entry: RepoEntry,
    workspace_root: Path,
    config: ToolConfig,
    *,
    command: list[str],
    capture_output: bool,
    dry_run: bool,
    header: Callable[[str, Path], None] | None,
) -> ForeachAction:
    try:
        spec = parse_repo_spec(entry.repo, default_forge=config.default_forge)
    except RepoSpecError as e:
        return ForeachAction(
            repo=entry.repo,
            short_name=entry.repo,
            action="error",
            message=str(e),
        )

    worktree = workspace_root / spec.name
    if not worktree.exists() or not worktree.is_dir():
        return ForeachAction(
            repo=entry.repo,
            short_name=spec.name,
            action="skipped",
            message=f"worktree missing at {worktree}",
        )

    if dry_run:
        return ForeachAction(
            repo=entry.repo,
            short_name=spec.name,
            action="would_run",
            message=f"would run {command} in {worktree}",
        )

    if header is not None:
        header(spec.name, worktree)

    try:
        stdout: str | None = None
        stderr: str | None = None
        if capture_output:
            captured = subprocess.run(
                command,
                cwd=str(worktree),
                capture_output=True,
                text=True,
                check=False,
            )
            stdout = captured.stdout
            stderr = captured.stderr
            exit_code = captured.returncode
        else:
            # Inherit parent stdout/stderr by passing None — the subprocess
            # writes directly to the parent's file descriptors so output
            # streams live in interactive use. In test environments where
            # the parent's stdout has no underlying fd (CliRunner), this
            # still works because None means "inherit the actual fd".
            inherited = subprocess.run(
                command,
                cwd=str(worktree),
                stdout=None,
                stderr=None,
                check=False,
            )
            exit_code = inherited.returncode
    except FileNotFoundError as e:
        return ForeachAction(
            repo=entry.repo,
            short_name=spec.name,
            action="error",
            message=f"command not found: {e}",
        )

    action_type: ForeachActionType = "ok" if exit_code == 0 else "failed"
    return ForeachAction(
        repo=entry.repo,
        short_name=spec.name,
        action=action_type,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
    )
