"""Service: remove a workspace, with a strict deletion safety contract.

Implements the policy in ``docs/initial-design.md §7.5``.

**Safety contract.** brunch will delete only:

1. the workspace's marker file (``brunch.toml``), only when nothing else stays;
2. directories the manifest declares as worktrees (via
   ``git worktree remove``, never ``shutil.rmtree``);
3. the workspace directory itself, **only when it is empty** after (1)+(2).

Anything else under the workspace root — sibling directories, dotfiles,
nested git repos, symlinks, files brunch never put there — is preserved
and the outcome is reported as ``partial``; ``brunch.toml`` then stays, minus
the repos whose worktrees were removed. With ``--force``, the entire
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
from brunch.manifest import load_workspace_manifest, write_workspace_manifest
from brunch.models import (
    RepoEntry,
    RmActionType,
    RmOutcome,
    RmRepoAction,
    ToolConfig,
    WorkspaceLocation,
    WorkspaceManifest,
)
from brunch.paths import canonical_clone_path, parse_repo_spec
from brunch.services.risk import assess_repo, clones_to_refresh, refresh_remotes

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
    skip_archive: bool = False,
    fetch: bool = True,
) -> RmOutcome:
    """Remove ``location``'s workspace, archiving first when ``force`` is set.

    ``skip_archive`` is an internal escape hatch used by :func:`rm_set` to
    avoid double-archiving each member when the whole set has already been
    captured in one tarball. Not meant for direct CLI use.

    Unless ``fetch`` is False, every remote of each repo's clone is fetched and
    pruned first (also on a dry run), so the verdict rests on current refs; a
    failed fetch is only a warning in the outcome (``fetch_warnings``): the
    verdict then rests on the remote refs from the last fetch.
    """

    if location.mode != "workspace":
        raise WorkspaceNotFoundError(
            f"rm_workspace requires a workspace location (got mode={location.mode!r})",
            hint="cd into one of the child workspaces, or pass -w <path>.",
        )

    _refuse_dangerous_root(location.root)

    manifest = load_workspace_manifest(location.manifest_path)
    fetch_warnings = (
        refresh_remotes(clones_to_refresh(manifest.repos, location.root, config)) if fetch else []
    )
    risks = [assess_repo(entry, location.root, config) for entry in manifest.repos]
    real_risks = [r for r in risks if r.is_at_risk]
    merged = [r for r in risks if r.merged_upstream and not r.is_at_risk]

    if real_risks and not force:
        return RmOutcome(
            workspace_name=manifest.name,
            workspace_path=location.root,
            fetch_warnings=fetch_warnings,
            merged=merged,
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
        planned_failed = any(a.action == "error" for a in planned_actions)
        planned_outcome: RmActionType = (
            "partial" if planned_preserved or planned_failed else "would_remove"
        )
        planned_dropped = (
            _entries_gone(manifest, planned_actions) if planned_outcome == "partial" else []
        )
        return RmOutcome(
            workspace_name=manifest.name,
            workspace_path=location.root,
            fetch_warnings=fetch_warnings,
            merged=merged,
            action=planned_outcome,
            risks=real_risks,
            repo_actions=planned_actions,
            preserved=planned_preserved,
            manifest_entries_dropped=planned_dropped,
            forced=force,
            dry_run=True,
        )

    # --force: archive everything (including any preserved content) before
    # any destructive action. Fail-closed: if the archive can't be written,
    # don't remove anything.
    archive_path: Path | None = None
    if force and not skip_archive:
        archive_path = _archive_or_raise(location.root, manifest.name)

    actions, preserved, outcome_action, dropped = _remove_workspace_in_place(
        location.root,
        manifest,
        declared_paths,
        config,
        force=force,
        manifest_filename=MANIFEST_FILENAME,
    )

    return RmOutcome(
        workspace_name=manifest.name,
        workspace_path=location.root,
        fetch_warnings=fetch_warnings,
        merged=merged,
        action=outcome_action,
        risks=real_risks,
        repo_actions=actions,
        preserved=preserved,
        manifest_entries_dropped=dropped,
        archive_path=archive_path,
        forced=force,
    )


def archive_or_raise(root: Path, name: str) -> Path:
    """Archive ``root`` to the default archive dir or raise BrunchError.

    Exposed for :mod:`brunch.services.set_ops`, which archives the whole set
    once before delegating to per-member removals.
    """

    return _archive_or_raise(root, name)


def _archive_or_raise(root: Path, name: str) -> Path:
    """Archive ``root`` to the default archive dir or raise BrunchError."""

    try:
        return create_workspace_archive(
            root,
            workspace_name=name,
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


def _remove_workspace_in_place(
    root: Path,
    manifest: WorkspaceManifest,
    declared_paths: set[Path],
    config: ToolConfig,
    *,
    force: bool,
    manifest_filename: str,
) -> tuple[list[RmRepoAction], list[Path], RmActionType, list[str]]:
    """Run the per-repo removal + safety-aware dir cleanup.

    No archive is created here; callers that want one must arrange it
    *before* invoking this function so a failure to archive can short-
    circuit the destruction. Returns (repo_actions, preserved, outcome,
    repos dropped from the manifest).

    When the workspace directory stays, ``brunch.toml`` stays too, minus the
    repos whose worktrees are gone, so ``status``, ``fsck`` and ``sync`` do not
    see them as missing. Entries whose removal failed remain.
    """

    actions: list[RmRepoAction] = []
    canonicals_touched: set[Path] = set()
    for entry in manifest.repos:
        action, canonical_used = _remove_one(entry, root, config, force=force)
        actions.append(action)
        if canonical_used is not None:
            canonicals_touched.add(canonical_used)

    # Best-effort prune of dangling refs in each touched canonical.
    for canonical in canonicals_touched:
        try:
            git.worktree_prune(canonical)
        except GitError:
            pass

    # Apply the safety contract: only remove the marker + the workspace dir
    # if nothing unknown remains. Never `rmtree` the workspace.
    preserved = _enumerate_preserved(root, declared_paths)
    failed = [a for a in actions if a.action == "error"]
    if preserved or failed:
        dropped = _drop_gone_entries(root / manifest_filename, manifest, actions)
        return actions, preserved, "partial", dropped
    outcome: RmActionType

    manifest_file = root / manifest_filename
    if manifest_file.is_file():
        try:
            manifest_file.unlink()
        except OSError:
            preserved = _enumerate_preserved(root, declared_paths)
    if not preserved and root.exists():
        try:
            root.rmdir()
            outcome = "removed"
        except OSError:
            preserved = _enumerate_preserved(root, declared_paths)
            outcome = "partial"
    else:
        outcome = "partial" if preserved else "removed"

    return actions, preserved, outcome, []


def _drop_gone_entries(
    manifest_path: Path, manifest: WorkspaceManifest, actions: list[RmRepoAction]
) -> list[str]:
    """Rewrite ``manifest_path`` without the repos whose worktrees are gone; return them."""

    dropped = _entries_gone(manifest, actions)
    kept = [entry for entry in manifest.repos if entry.repo not in dropped]
    write_workspace_manifest(manifest_path, manifest.model_copy(update={"repos": kept}))
    return dropped


def _entries_gone(manifest: WorkspaceManifest, actions: list[RmRepoAction]) -> list[str]:
    """The repos whose worktree was, or would be, removed or found already absent."""

    failed = {a.repo for a in actions if a.action == "error"}
    return [entry.repo for entry in manifest.repos if entry.repo not in failed]


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
        canonical = canonical_clone_path(spec, root=config.root)
        if not canonical.exists() or not git.is_git_repo(canonical):
            actions.append(
                RmRepoAction(
                    repo=entry.repo,
                    short_name=spec.name,
                    action="error",
                    message=_missing_canonical_message(canonical, worktree),
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


def _missing_canonical_message(canonical: Path, worktree: Path) -> str:
    return (
        f"canonical clone missing at {canonical}; cannot use "
        "`git worktree remove`. Re-clone the canonical or "
        f"remove {worktree} manually."
    )


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
                message=_missing_canonical_message(canonical, worktree),
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
