"""Service: fan out ``git pull`` across all repos in a workspace."""

from __future__ import annotations

from pathlib import Path

from brunch import git
from brunch.errors import GitError, RepoSpecError, WorkspaceNotFoundError
from brunch.manifest import load_workspace_manifest
from brunch.models import (
    PullAction,
    PullReport,
    RepoEntry,
    ToolConfig,
    WorkspaceLocation,
)
from brunch.paths import parse_repo_spec


def pull_workspace(
    location: WorkspaceLocation,
    config: ToolConfig,
    *,
    dry_run: bool = False,
) -> PullReport:
    """Run ``git pull`` in each repo's worktree."""

    if location.mode != "workspace":
        raise WorkspaceNotFoundError(
            f"pull at set roots isn't supported yet (got mode={location.mode!r})",
            hint="cd into one of the child workspaces, or pass -w <path>.",
        )

    manifest = load_workspace_manifest(location.manifest_path)
    actions = [_pull_one(entry, location.root, config, dry_run=dry_run) for entry in manifest.repos]
    return PullReport(
        workspace_name=manifest.name,
        workspace_path=location.root,
        actions=actions,
        dry_run=dry_run,
    )


def _pull_one(
    entry: RepoEntry,
    workspace_root: Path,
    config: ToolConfig,
    *,
    dry_run: bool,
) -> PullAction:
    try:
        spec = parse_repo_spec(entry.repo, default_forge=config.default_forge)
    except RepoSpecError as e:
        return PullAction(
            repo=entry.repo,
            short_name=entry.repo,
            action="error",
            message=str(e),
            hint=e.hint,
        )

    worktree = workspace_root / spec.name
    if not worktree.exists() or not git.is_git_repo(worktree):
        return PullAction(
            repo=entry.repo,
            short_name=spec.name,
            action="skipped",
            message=f"worktree missing at {worktree}",
            hint="run `brunch sync` first",
        )

    if not git.has_remote(worktree):
        return PullAction(
            repo=entry.repo,
            short_name=spec.name,
            action="skipped",
            message="no remote configured",
        )

    if dry_run:
        return PullAction(
            repo=entry.repo,
            short_name=spec.name,
            action="would_pull",
            message=f"would pull in {worktree}",
        )

    try:
        git.pull(worktree)
    except GitError as e:
        return PullAction(
            repo=entry.repo,
            short_name=spec.name,
            action="error",
            message=str(e),
            hint=(
                "resolve the underlying git issue (conflicts, dirty worktree, "
                "no upstream) and retry."
            ),
        )

    return PullAction(
        repo=entry.repo,
        short_name=spec.name,
        action="pulled",
        message="pulled from default remote",
    )
