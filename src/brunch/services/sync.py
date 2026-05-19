"""Service: reconcile on-disk worktrees with the workspace manifest.

The drift policy lives in `docs/initial-design.md §7.3`. The short version:
``sync`` only takes additive, non-destructive action — it creates missing
worktrees and warns about anything else.
"""

from __future__ import annotations

from pathlib import Path

from brunch import git
from brunch.errors import RepoSpecError, WorkspaceNotFoundError
from brunch.manifest import load_workspace_manifest
from brunch.models import (
    RepoEntry,
    RepoSpec,
    SyncAction,
    SyncReport,
    ToolConfig,
    WorkspaceLocation,
)
from brunch.paths import canonical_clone_path, parse_repo_spec


def sync_workspace(
    location: WorkspaceLocation,
    config: ToolConfig,
    *,
    dry_run: bool = False,
) -> SyncReport:
    """Run a sync pass against ``location``.

    Returns a structured report. When ``dry_run`` is true, no side effects
    are performed but the report still describes what *would* happen.
    """

    if location.mode != "workspace":
        raise WorkspaceNotFoundError(
            f"sync at set roots isn't supported yet (got mode={location.mode!r})",
            hint="cd into one of the child workspaces, or pass -w <path>.",
        )

    manifest = load_workspace_manifest(location.manifest_path)
    actions: list[SyncAction] = []
    for entry in manifest.repos:
        actions.append(_reconcile_one(entry, location.root, config, dry_run=dry_run))

    return SyncReport(
        workspace_name=manifest.name,
        workspace_path=location.root,
        actions=actions,
        dry_run=dry_run,
    )


def _reconcile_one(
    entry: RepoEntry,
    workspace_root: Path,
    config: ToolConfig,
    *,
    dry_run: bool,
) -> SyncAction:
    """Compute (and optionally apply) the reconciliation for one [[repo]]."""

    try:
        spec = parse_repo_spec(entry.repo, default_forge=config.default_forge)
    except RepoSpecError as e:
        return SyncAction(
            repo=entry.repo,
            short_name=entry.repo,
            action="error",
            message=str(e),
            hint=e.hint,
        )

    canonical = canonical_clone_path(spec, root=config.root)
    worktree = workspace_root / spec.name

    if not canonical.exists():
        return SyncAction(
            repo=entry.repo,
            short_name=spec.name,
            action="error",
            message=f"canonical clone not found at {canonical}",
            hint=f"clone it: `gh repo clone {spec.short} {canonical}` (or via ghq)",
        )
    if not git.is_git_repo(canonical):
        return SyncAction(
            repo=entry.repo,
            short_name=spec.name,
            action="error",
            message=f"{canonical} exists but is not a git repository",
        )

    if not worktree.exists():
        return _create_worktree(entry, spec, canonical, worktree, dry_run=dry_run)

    if not git.is_git_repo(worktree):
        return SyncAction(
            repo=entry.repo,
            short_name=spec.name,
            action="warning",
            message=f"worktree at {worktree} exists but git can't read it",
            hint=f"try `git -C {canonical} worktree repair`",
        )

    actual = git.current_branch(worktree)
    if actual != entry.branch:
        return SyncAction(
            repo=entry.repo,
            short_name=spec.name,
            action="warning",
            message=(f"worktree is on {actual!r}, manifest declares {entry.branch!r}"),
            hint="update the manifest, or switch the worktree branch deliberately",
        )

    st = git.get_status(worktree)
    if st.has_uncommitted or st.has_untracked:
        bits = []
        if st.has_uncommitted:
            bits.append("uncommitted changes")
        if st.has_untracked:
            bits.append("untracked files")
        return SyncAction(
            repo=entry.repo,
            short_name=spec.name,
            action="warning",
            message="worktree has " + " and ".join(bits),
        )

    return SyncAction(
        repo=entry.repo,
        short_name=spec.name,
        action="ok",
        message="up to date",
    )


def _create_worktree(
    entry: RepoEntry,
    spec: RepoSpec,
    canonical: Path,
    worktree: Path,
    *,
    dry_run: bool,
) -> SyncAction:
    # Pre-flight: branch already checked out elsewhere?
    try:
        refs = git.worktree_list(canonical)
    except Exception as e:  # GitError or similar
        return SyncAction(
            repo=entry.repo,
            short_name=spec.name,
            action="error",
            message=str(e),
        )

    conflict = next(
        (r for r in refs if r.branch == entry.branch and r.path != worktree),
        None,
    )
    if conflict is not None:
        return SyncAction(
            repo=entry.repo,
            short_name=spec.name,
            action="error",
            message=(f"branch {entry.branch!r} is already checked out at {conflict.path}"),
            hint="pick a different branch, or remove the conflicting worktree",
        )

    if dry_run:
        return SyncAction(
            repo=entry.repo,
            short_name=spec.name,
            action="created",
            message=f"would create worktree at {worktree} on {entry.branch!r}",
        )

    try:
        git.add_worktree(canonical, worktree, branch=entry.branch, base=entry.base)
    except Exception as e:
        return SyncAction(
            repo=entry.repo,
            short_name=spec.name,
            action="error",
            message=str(e),
        )

    return SyncAction(
        repo=entry.repo,
        short_name=spec.name,
        action="created",
        message=f"created worktree at {worktree} on {entry.branch!r}",
    )
