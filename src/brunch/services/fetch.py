"""Service: fan out ``git fetch`` across all repos in a workspace."""

from __future__ import annotations

from pathlib import Path

from brunch import git
from brunch.errors import GitError, RepoSpecError, WorkspaceNotFoundError
from brunch.manifest import load_workspace_manifest
from brunch.models import (
    FetchAction,
    FetchReport,
    RepoEntry,
    ToolConfig,
    WorkspaceLocation,
)
from brunch.paths import parse_repo_spec


def fetch_workspace(
    location: WorkspaceLocation,
    config: ToolConfig,
    *,
    dry_run: bool = False,
) -> FetchReport:
    """Run ``git fetch`` in each repo's worktree."""

    if location.mode != "workspace":
        raise WorkspaceNotFoundError(
            f"fetch at set roots isn't supported yet (got mode={location.mode!r})",
            hint="cd into one of the child workspaces, or pass -w <path>.",
        )

    manifest = load_workspace_manifest(location.manifest_path)
    actions = [
        _fetch_one(entry, location.root, config, dry_run=dry_run) for entry in manifest.repos
    ]
    return FetchReport(
        workspace_name=manifest.name,
        workspace_path=location.root,
        actions=actions,
        dry_run=dry_run,
    )


def _fetch_one(
    entry: RepoEntry,
    workspace_root: Path,
    config: ToolConfig,
    *,
    dry_run: bool,
) -> FetchAction:
    try:
        spec = parse_repo_spec(entry.repo, default_forge=config.default_forge)
    except RepoSpecError as e:
        return FetchAction(
            repo=entry.repo,
            short_name=entry.repo,
            action="error",
            message=str(e),
            hint=e.hint,
        )

    worktree = workspace_root / spec.name
    if not worktree.exists() or not git.is_git_repo(worktree):
        return FetchAction(
            repo=entry.repo,
            short_name=spec.name,
            action="skipped",
            message=f"worktree missing at {worktree}",
            hint="run `brunch sync` first",
        )

    if not git.has_remote(worktree):
        return FetchAction(
            repo=entry.repo,
            short_name=spec.name,
            action="skipped",
            message="no remote configured",
        )

    if dry_run:
        return FetchAction(
            repo=entry.repo,
            short_name=spec.name,
            action="would_fetch",
            message=f"would fetch in {worktree}",
        )

    try:
        git.fetch(worktree)
    except GitError as e:
        return FetchAction(
            repo=entry.repo,
            short_name=spec.name,
            action="error",
            message=str(e),
        )

    return FetchAction(
        repo=entry.repo,
        short_name=spec.name,
        action="fetched",
        message="fetched from default remote",
    )
