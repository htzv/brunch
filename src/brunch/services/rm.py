"""Service: remove a workspace, with optional archive-on-force safety net.

Implements the policy in ``docs/initial-design.md §7.5``:

- Refuse by default if any repo is dirty (uncommitted, untracked, unpushed
  commits) or has a local-only branch with commits beyond its base. Print
  the per-repo reasons.
- With ``--force``, archive the entire workspace dir under
  ``~/.local/share/brunch/archives/<name>-<UTC>.tar.gz`` *before* any
  destructive action, then remove worktrees via ``git worktree remove
  --force``, prune dangling refs in each canonical, and ``rmtree`` the
  workspace.
- Branches are deliberately **not** deleted — they stay in the canonical
  clone and can be re-materialised as worktrees later.
- ``--dry-run`` shows the full plan without acting.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from brunch import git
from brunch.archive import create_workspace_archive, default_archive_dir
from brunch.errors import GitError, RepoSpecError, WorkspaceNotFoundError
from brunch.manifest import load_workspace_manifest
from brunch.models import (
    RepoEntry,
    RmOutcome,
    RmRepoAction,
    RmRisk,
    ToolConfig,
    WorkspaceLocation,
    WorkspaceManifest,
)
from brunch.paths import canonical_clone_path, parse_repo_spec


def rm_workspace(
    location: WorkspaceLocation,
    config: ToolConfig,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> RmOutcome:
    """Remove ``location``'s workspace, archiving first when ``force`` is set."""

    if location.mode != "workspace":
        raise WorkspaceNotFoundError(
            f"rm at set roots isn't supported yet (got mode={location.mode!r})",
            hint="cd into one of the child workspaces, or pass -w <path>.",
        )

    manifest = load_workspace_manifest(location.manifest_path)
    risks = _assess_risks(manifest, location.root, config)
    real_risks = [r for r in risks if r.is_at_risk]

    if real_risks and not force:
        return RmOutcome(
            workspace_name=manifest.name,
            workspace_path=location.root,
            action="refused",
            risks=real_risks,
            forced=False,
            dry_run=dry_run,
        )

    # Plan-only mode.
    if dry_run:
        return RmOutcome(
            workspace_name=manifest.name,
            workspace_path=location.root,
            action="would_remove",
            risks=real_risks,
            repo_actions=_plan_removals(manifest, location.root, config),
            forced=force,
            dry_run=True,
        )

    # --force: archive before destroying anything.
    archive_path: Path | None = None
    if force:
        archive_path = create_workspace_archive(
            location.root,
            workspace_name=manifest.name,
            archive_dir=default_archive_dir(),
        )

    # Per-repo removal pass.
    repo_actions: list[RmRepoAction] = []
    canonicals_touched: set[Path] = set()
    for entry in manifest.repos:
        action, canonical_used = _remove_one(entry, location.root, config, force=force)
        repo_actions.append(action)
        if canonical_used is not None:
            canonicals_touched.add(canonical_used)

    # Best-effort prune in each touched canonical.
    for canonical in canonicals_touched:
        try:
            git.worktree_prune(canonical)
        except GitError:
            # Prune is opportunistic — don't fail the whole rm because of it.
            pass

    # Finally remove the workspace directory itself.
    if location.root.exists():
        shutil.rmtree(location.root)

    return RmOutcome(
        workspace_name=manifest.name,
        workspace_path=location.root,
        action="removed",
        risks=real_risks,
        repo_actions=repo_actions,
        archive_path=archive_path,
        forced=force,
    )


# ---------------------------------------------------------------------------
# Risk assessment


def _assess_risks(
    manifest: WorkspaceManifest, workspace_root: Path, config: ToolConfig
) -> list[RmRisk]:
    """Compute the per-repo risks that ``--force`` would override."""

    risks: list[RmRisk] = []
    for entry in manifest.repos:
        risks.append(_assess_one(entry, workspace_root, config))
    return risks


def _assess_one(entry: RepoEntry, workspace_root: Path, config: ToolConfig) -> RmRisk:
    try:
        spec = parse_repo_spec(entry.repo, default_forge=config.default_forge)
    except RepoSpecError:
        return RmRisk(repo=entry.repo, short_name=entry.repo)

    worktree = workspace_root / spec.name
    if not worktree.exists() or not git.is_git_repo(worktree):
        # Nothing to risk losing — there's no worktree.
        return RmRisk(repo=entry.repo, short_name=spec.name)

    try:
        st = git.get_status(worktree)
    except GitError:
        # If we can't read status, be conservative and flag it.
        return RmRisk(
            repo=entry.repo,
            short_name=spec.name,
            has_uncommitted=True,
        )

    if st.upstream:
        unpushed = st.ahead
        no_upstream = False
    else:
        # No upstream: any commits beyond <base> are local-only.
        unpushed = git.count_commits_ahead_of(worktree, entry.base)
        no_upstream = unpushed > 0

    return RmRisk(
        repo=entry.repo,
        short_name=spec.name,
        has_uncommitted=st.has_uncommitted,
        has_untracked=st.has_untracked,
        unpushed_commits=unpushed,
        no_upstream=no_upstream,
    )


# ---------------------------------------------------------------------------
# Removal pass


def _plan_removals(
    manifest: WorkspaceManifest, workspace_root: Path, config: ToolConfig
) -> list[RmRepoAction]:
    actions: list[RmRepoAction] = []
    for entry in manifest.repos:
        try:
            spec = parse_repo_spec(entry.repo, default_forge=config.default_forge)
        except RepoSpecError as e:
            actions.append(
                RmRepoAction(
                    repo=entry.repo,
                    short_name=entry.repo,
                    action="error",
                    message=str(e),
                )
            )
            continue
        worktree = workspace_root / spec.name
        if not worktree.exists():
            actions.append(
                RmRepoAction(
                    repo=entry.repo,
                    short_name=spec.name,
                    action="skipped",
                    message=f"worktree already absent at {worktree}",
                )
            )
            continue
        actions.append(
            RmRepoAction(
                repo=entry.repo,
                short_name=spec.name,
                action="would_remove",
                message=f"would `git worktree remove` at {worktree}",
            )
        )
    return actions


def _remove_one(
    entry: RepoEntry,
    workspace_root: Path,
    config: ToolConfig,
    *,
    force: bool,
) -> tuple[RmRepoAction, Path | None]:
    try:
        spec = parse_repo_spec(entry.repo, default_forge=config.default_forge)
    except RepoSpecError as e:
        return (
            RmRepoAction(
                repo=entry.repo,
                short_name=entry.repo,
                action="error",
                message=str(e),
            ),
            None,
        )

    canonical = canonical_clone_path(spec, root=config.root)
    worktree = workspace_root / spec.name

    if not worktree.exists():
        return (
            RmRepoAction(
                repo=entry.repo,
                short_name=spec.name,
                action="skipped",
                message=f"worktree already absent at {worktree}",
            ),
            canonical if canonical.exists() else None,
        )

    if not canonical.exists() or not git.is_git_repo(canonical):
        # No canonical to talk to. Just rmtree the dir so the workspace can go.
        try:
            shutil.rmtree(worktree)
        except OSError as e:
            return (
                RmRepoAction(
                    repo=entry.repo,
                    short_name=spec.name,
                    action="error",
                    message=f"failed to remove {worktree}: {e}",
                ),
                None,
            )
        return (
            RmRepoAction(
                repo=entry.repo,
                short_name=spec.name,
                action="removed",
                message=f"removed {worktree} (canonical unreachable, "
                "dangling refs will need manual pruning)",
            ),
            None,
        )

    try:
        # When force=True, we've already archived; pass force to git so it
        # doesn't refuse on local changes.
        git.remove_worktree(canonical, worktree, force=force)
    except GitError as e:
        return (
            RmRepoAction(
                repo=entry.repo,
                short_name=spec.name,
                action="error",
                message=str(e),
            ),
            canonical,
        )

    return (
        RmRepoAction(
            repo=entry.repo,
            short_name=spec.name,
            action="removed",
            message=f"removed worktree at {worktree}",
        ),
        canonical,
    )
