"""Service: drop a single repo's worktree from a workspace.

The per-repo analogue of ``br rm``. It reuses the same deletion safety contract
— refuse on uncommitted / untracked / unpushed / no-upstream work unless
``--force`` — but touches only the one repo: ``git worktree remove`` on its
worktree plus its ``[[repo]]`` manifest entry. The rest of the workspace and the
shared canonical clone are left intact (the branch survives in the canonical).
"""

from __future__ import annotations

from brunch import git
from brunch.errors import BrunchError, GitError, RepoSpecError, WorkspaceNotFoundError
from brunch.manifest import load_workspace_manifest, write_workspace_manifest
from brunch.models import (
    DropOutcome,
    RepoEntry,
    RmRisk,
    ToolConfig,
    WorkspaceLocation,
    WorkspaceManifest,
)
from brunch.paths import canonical_clone_path, parse_repo_spec
from brunch.services.risk import assess_repo, clones_to_refresh, refresh_remotes


def drop_repo(
    location: WorkspaceLocation,
    config: ToolConfig,
    selector: str,
    *,
    force: bool = False,
    dry_run: bool = False,
    fetch: bool = True,
) -> DropOutcome:
    """Remove one repo's worktree + manifest entry. Refuses risky removals sans ``force``.

    Unless ``fetch`` is False, the repo's remotes are fetched and pruned first.
    """

    if location.mode != "workspace":
        raise WorkspaceNotFoundError(
            f"drop requires a workspace location (got mode={location.mode!r})",
            hint="cd into a workspace, or pass -w <path>.",
        )

    manifest = load_workspace_manifest(location.manifest_path)
    entry, short = _resolve_entry(manifest, selector, config)
    worktree = location.root / short

    if fetch:
        refresh_remotes(clones_to_refresh([entry], location.root, config))
    risk = assess_repo(entry, location.root, config)

    def _outcome(
        action: str, *, risk: RmRisk | None = None, message: str | None = None
    ) -> DropOutcome:
        return DropOutcome(
            workspace_name=manifest.name,
            workspace_path=location.root,
            repo=entry.repo,
            short_name=short,
            worktree_path=worktree,
            action=action,  # type: ignore[arg-type]
            dry_run=dry_run,
            risk=risk,
            message=message,
        )

    # Risk beats dry-run: a refusal is reported the same either way.
    if risk.is_at_risk and not force:
        return _outcome("refused", risk=risk, message="uncommitted/unpushed work — use --force")

    if dry_run:
        return _outcome(
            "would_drop",
            risk=risk if risk.is_at_risk else None,
            message=f"would `git worktree remove` at {worktree}",
        )

    if not worktree.exists():
        _drop_entry(manifest, entry, location)
        return _outcome("dropped", message="worktree already absent; manifest entry removed")

    spec = parse_repo_spec(entry.repo, default_forge=config.default_forge)
    canonical = canonical_clone_path(spec, root=config.root)
    if not canonical.exists() or not git.is_git_repo(canonical):
        return _outcome(
            "error",
            message=(
                f"canonical clone missing at {canonical}; cannot `git worktree remove`. "
                f"Re-clone it, or remove {worktree} manually."
            ),
        )

    try:
        git.remove_worktree(canonical, worktree, force=force)
    except GitError as e:
        return _outcome("error", message=str(e))
    try:
        git.worktree_prune(canonical)
    except GitError:
        pass

    _drop_entry(manifest, entry, location)
    return _outcome("dropped", message=f"removed worktree at {worktree}")


def _resolve_entry(
    manifest: WorkspaceManifest, selector: str, config: ToolConfig
) -> tuple[RepoEntry, str]:
    """Find the manifest entry matching ``selector`` (short name or spec form)."""

    names: list[str] = []
    for entry in manifest.repos:
        try:
            spec = parse_repo_spec(entry.repo, default_forge=config.default_forge)
        except RepoSpecError:
            if selector == entry.repo:
                return entry, entry.repo
            continue
        names.append(spec.name)
        if selector in (spec.name, spec.short, spec.qualified, entry.repo):
            return entry, spec.name

    available = ", ".join(sorted(names)) or "(none)"
    raise BrunchError(
        f"repo {selector!r} is not in this workspace.",
        hint=f"available repos: {available}.",
    )


def _drop_entry(manifest: WorkspaceManifest, entry: RepoEntry, location: WorkspaceLocation) -> None:
    """Remove ``entry`` from the manifest and persist. Repo specs are unique per workspace."""

    manifest.repos = [r for r in manifest.repos if r.repo != entry.repo]
    write_workspace_manifest(location.manifest_path, manifest)
