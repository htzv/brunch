"""Service: remove a workspace, with a strict deletion safety contract.

Implements the policy in ``docs/initial-design.md §7.5``.

**Safety contract.** brunch will delete only:

1. the workspace's marker file (``brunch.toml``);
2. directories the manifest declares as worktrees (via
   ``git worktree remove``, never ``shutil.rmtree``);
3. the workspace directory itself, **only when it is empty** after (1)+(2).

Anything else under the workspace root — sibling directories, dotfiles,
nested git repos, symlinks, files brunch never put there — is preserved
and the outcome is reported as ``partial``. With ``--force``, the entire
workspace is archived first (so preserved content is captured in the
tarball too), but the deletion contract still applies. If archive
creation fails, the removal is aborted.

Additionally, the service refuses to operate on dangerously short paths
(filesystem root, ``$HOME``, etc.) regardless of any other flag.
"""

from __future__ import annotations

import os
from pathlib import Path

from brunch import git
from brunch.archive import create_workspace_archive, default_archive_dir
from brunch.errors import BrunchError, GitError, RepoSpecError, WorkspaceNotFoundError
from brunch.manifest import load_workspace_manifest
from brunch.models import (
    RepoEntry,
    RmActionType,
    RmOutcome,
    RmRepoAction,
    RmRisk,
    ToolConfig,
    WorkspaceLocation,
    WorkspaceManifest,
)
from brunch.paths import canonical_clone_path, parse_repo_spec

MANIFEST_FILENAME = "brunch.toml"
# Reserved for future brunch-owned state (e.g. lockfiles in iteration 3+).
# Listed here so the safety contract recognises and removes it when empty.
RESERVED_BRUNCH_NAMES: frozenset[str] = frozenset({MANIFEST_FILENAME, ".brunch"})


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

    _refuse_dangerous_root(location.root)

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

    # Paths the manifest claims ownership of. These are the only ones we'll
    # remove (via git); everything else under the workspace root is preserved.
    declared_paths = _declared_worktree_paths(manifest, location.root, config)

    if dry_run:
        planned_actions = _plan_removals(manifest, location.root, config)
        planned_preserved = _enumerate_preserved(location.root, declared_paths)
        planned_outcome: RmActionType = "partial" if planned_preserved else "would_remove"
        return RmOutcome(
            workspace_name=manifest.name,
            workspace_path=location.root,
            action=planned_outcome,
            risks=real_risks,
            repo_actions=planned_actions,
            preserved=planned_preserved,
            forced=force,
            dry_run=True,
        )

    # --force: archive everything (including any preserved content) before
    # any destructive action. Fail-closed: if the archive can't be written,
    # don't remove anything.
    archive_path: Path | None = None
    if force:
        try:
            archive_path = create_workspace_archive(
                location.root,
                workspace_name=manifest.name,
                archive_dir=default_archive_dir(),
            )
        except OSError as e:
            raise BrunchError(
                f"failed to write archive: {e}",
                hint=(
                    "removal aborted to avoid losing data; resolve the archive "
                    "write failure (disk space, permissions on "
                    f"{default_archive_dir()}) and retry."
                ),
            ) from e

    # Per-repo removal.
    actions: list[RmRepoAction] = []
    canonicals_touched: set[Path] = set()
    for entry in manifest.repos:
        action, canonical_used = _remove_one(entry, location.root, config, force=force)
        actions.append(action)
        if canonical_used is not None:
            canonicals_touched.add(canonical_used)

    # Best-effort prune of dangling refs in each touched canonical.
    for canonical in canonicals_touched:
        try:
            git.worktree_prune(canonical)
        except GitError:
            pass

    # Apply the safety contract: only remove brunch.toml + the workspace dir
    # if nothing unknown remains. Never `rmtree` the workspace.
    preserved = _enumerate_preserved(location.root, declared_paths)
    outcome_action: RmActionType
    if preserved:
        outcome_action = "partial"
    else:
        # Safe to remove the marker + an empty workspace dir.
        manifest_file = location.root / MANIFEST_FILENAME
        if manifest_file.is_file():
            try:
                manifest_file.unlink()
            except OSError:
                # Could not delete the marker — leave everything else alone.
                preserved = _enumerate_preserved(location.root, declared_paths)
        if not preserved and location.root.exists():
            try:
                location.root.rmdir()
                outcome_action = "removed"
            except OSError:
                # Something else snuck in (race) or rmdir was denied. Recompute
                # preserved to reflect reality and downgrade to partial.
                preserved = _enumerate_preserved(location.root, declared_paths)
                outcome_action = "partial"
        else:
            outcome_action = "partial" if preserved else "removed"

    return RmOutcome(
        workspace_name=manifest.name,
        workspace_path=location.root,
        action=outcome_action,
        risks=real_risks,
        repo_actions=actions,
        preserved=preserved,
        archive_path=archive_path,
        forced=force,
    )


# ---------------------------------------------------------------------------
# Safety guards


def _refuse_dangerous_root(path: Path) -> None:
    """Refuse to operate on filesystem root, $HOME, or other suspicious paths."""

    try:
        resolved = path.resolve(strict=False)
    except OSError:
        resolved = path

    # Filesystem root (/, C:\ on Windows, etc.) — never operate here.
    if str(resolved) == resolved.anchor:
        raise BrunchError(
            f"refusing to operate on filesystem root {resolved}",
            hint="this looks dangerous; check the -w argument or your cwd.",
        )

    # User's home directory.
    try:
        home = Path.home()
    except RuntimeError:
        home = None
    if home is not None and resolved == home:
        raise BrunchError(
            f"refusing to operate on home directory {resolved}",
            hint="point -w at a workspace directory, not your home.",
        )

    # Pathologically short absolute paths (e.g. /home, /var) — anything
    # with two or fewer components has too much blast radius if our model
    # is wrong about it.
    if resolved.is_absolute() and len(resolved.parts) <= 2:
        raise BrunchError(
            f"refusing to operate on a top-level path {resolved}",
            hint="this looks dangerous; pick a more specific workspace path.",
        )


# ---------------------------------------------------------------------------
# Enumeration


def _declared_worktree_paths(
    manifest: WorkspaceManifest, workspace_root: Path, config: ToolConfig
) -> set[Path]:
    """The absolute paths that the manifest declares as worktrees.

    Used to recognise which direct children of the workspace are
    brunch-owned (and therefore eligible for removal); everything else is
    preserved.
    """

    paths: set[Path] = set()
    for entry in manifest.repos:
        try:
            spec = parse_repo_spec(entry.repo, default_forge=config.default_forge)
        except RepoSpecError:
            continue
        candidate = workspace_root / spec.name
        try:
            paths.add(candidate.resolve(strict=False))
        except OSError:
            paths.add(candidate)
    return paths


def _enumerate_preserved(workspace_root: Path, declared_paths: set[Path]) -> list[Path]:
    """Return direct children of ``workspace_root`` that are NOT brunch-owned.

    Lists are sorted by name for stable output. Symlinks are listed as-is
    and never resolved+followed; entries we can't stat are still preserved
    (better to leave them alone than to ignore them).
    """

    preserved: list[Path] = []
    if not workspace_root.exists() or not workspace_root.is_dir():
        return preserved

    try:
        with os.scandir(workspace_root) as it:
            entries = sorted(it, key=lambda e: e.name)
    except OSError:
        return preserved

    for entry in entries:
        if entry.name in RESERVED_BRUNCH_NAMES:
            continue
        path = Path(entry.path)
        try:
            resolved = path.resolve(strict=False)
        except OSError:
            resolved = path
        if resolved in declared_paths:
            continue
        preserved.append(path)

    return preserved


# ---------------------------------------------------------------------------
# Risk assessment (unchanged from M4)


def _assess_risks(
    manifest: WorkspaceManifest, workspace_root: Path, config: ToolConfig
) -> list[RmRisk]:
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
        return RmRisk(repo=entry.repo, short_name=spec.name)

    try:
        st = git.get_status(worktree)
    except GitError:
        return RmRisk(
            repo=entry.repo,
            short_name=spec.name,
            has_uncommitted=True,
        )

    if st.upstream:
        unpushed = st.ahead
        no_upstream = False
    else:
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
# Per-repo removal


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
        # No canonical to talk to. Be conservative: report an error rather
        # than try to remove the dir ourselves; the safety contract reserves
        # rmtree for git's worktree machinery.
        return (
            RmRepoAction(
                repo=entry.repo,
                short_name=spec.name,
                action="error",
                message=(
                    f"canonical clone missing at {canonical}; cannot use "
                    "`git worktree remove`. Re-clone the canonical or "
                    f"remove {worktree} manually."
                ),
            ),
            None,
        )

    try:
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
