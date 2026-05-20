"""Set-mode entrypoints: fan a per-workspace service across all members.

Each function here matches the shape of its per-workspace counterpart so
the controllers can dispatch on ``location.mode`` cleanly. Set-level
aggregates are returned as the corresponding ``Set*Report`` model.
"""

from __future__ import annotations

import os
from pathlib import Path

from brunch.errors import WorkspaceNotFoundError
from brunch.manifest import load_set_manifest
from brunch.models import (
    SetFetchReport,
    SetForeachReport,
    SetFsckReport,
    SetPullReport,
    SetRebaseReport,
    SetRmActionType,
    SetRmOutcome,
    SetStatus,
    ToolConfig,
    WorkspaceLocation,
)
from brunch.paths import SET_MARKER, discover_set_members
from brunch.services.fetch import fetch_workspace
from brunch.services.foreach import foreach_workspace
from brunch.services.fsck import fsck_workspace
from brunch.services.pull import pull_workspace
from brunch.services.rebase import rebase_workspace
from brunch.services.rm import (
    _refuse_dangerous_root,
    archive_or_raise,
    rm_workspace,
)
from brunch.services.status import compute_workspace_status


def _require_set_mode(location: WorkspaceLocation, op: str) -> None:
    if location.mode != "set":
        raise WorkspaceNotFoundError(
            f"set-mode {op} requires a brunch-set.toml at the location "
            f"(got mode={location.mode!r})",
        )


def compute_set_status(location: WorkspaceLocation, config: ToolConfig) -> SetStatus:
    _require_set_mode(location, "status")
    manifest = load_set_manifest(location.manifest_path)
    members = discover_set_members(location.root)
    return SetStatus(
        set_name=manifest.name,
        set_path=location.root,
        description=manifest.description,
        members=[compute_workspace_status(m, config) for m in members],
    )


def fsck_set(location: WorkspaceLocation, config: ToolConfig) -> SetFsckReport:
    _require_set_mode(location, "fsck")
    manifest = load_set_manifest(location.manifest_path)
    members = discover_set_members(location.root)
    return SetFsckReport(
        set_name=manifest.name,
        set_path=location.root,
        members=[fsck_workspace(m, config) for m in members],
    )


def fetch_set(
    location: WorkspaceLocation,
    config: ToolConfig,
    *,
    dry_run: bool = False,
) -> SetFetchReport:
    _require_set_mode(location, "fetch")
    manifest = load_set_manifest(location.manifest_path)
    members = discover_set_members(location.root)
    return SetFetchReport(
        set_name=manifest.name,
        set_path=location.root,
        members=[fetch_workspace(m, config, dry_run=dry_run) for m in members],
        dry_run=dry_run,
    )


def pull_set(
    location: WorkspaceLocation,
    config: ToolConfig,
    *,
    dry_run: bool = False,
) -> SetPullReport:
    _require_set_mode(location, "pull")
    manifest = load_set_manifest(location.manifest_path)
    members = discover_set_members(location.root)
    return SetPullReport(
        set_name=manifest.name,
        set_path=location.root,
        members=[pull_workspace(m, config, dry_run=dry_run) for m in members],
        dry_run=dry_run,
    )


def rebase_set(
    location: WorkspaceLocation,
    config: ToolConfig,
    *,
    onto: str | None = None,
    autostash: bool = False,
    no_fetch: bool = False,
    continue_on_error: bool = False,
    dry_run: bool = False,
) -> SetRebaseReport:
    _require_set_mode(location, "rebase")
    manifest = load_set_manifest(location.manifest_path)
    members = discover_set_members(location.root)
    return SetRebaseReport(
        set_name=manifest.name,
        set_path=location.root,
        members=[
            rebase_workspace(
                m,
                config,
                onto=onto,
                autostash=autostash,
                no_fetch=no_fetch,
                continue_on_error=continue_on_error,
                dry_run=dry_run,
            )
            for m in members
        ],
        dry_run=dry_run,
    )


def foreach_set(
    location: WorkspaceLocation,
    config: ToolConfig,
    *,
    command: list[str],
    capture_output: bool = False,
    continue_on_error: bool = False,
    dry_run: bool = False,
) -> SetForeachReport:
    _require_set_mode(location, "foreach")
    manifest = load_set_manifest(location.manifest_path)
    members = discover_set_members(location.root)
    return SetForeachReport(
        set_name=manifest.name,
        set_path=location.root,
        command=command,
        members=[
            foreach_workspace(
                m,
                config,
                command=command,
                capture_output=capture_output,
                continue_on_error=continue_on_error,
                dry_run=dry_run,
            )
            for m in members
        ],
        dry_run=dry_run,
    )


def rm_set(
    location: WorkspaceLocation,
    config: ToolConfig,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> SetRmOutcome:
    """Remove a whole workspace set, archiving once and respecting the
    deletion safety contract at the set root.

    Members are processed via :func:`rm_workspace` with ``skip_archive=True``
    because the set tarball already captures the entire dir.
    """

    _require_set_mode(location, "rm")
    _refuse_dangerous_root(location.root)

    set_manifest = load_set_manifest(location.manifest_path)
    members = discover_set_members(location.root)

    # Phase 1: dry-run each member without forcing — surfaces refusals.
    previews = [rm_workspace(m, config, force=False, dry_run=True) for m in members]
    any_refused = any(p.action == "refused" for p in previews)

    if any_refused and not force:
        return SetRmOutcome(
            set_name=set_manifest.name,
            set_path=location.root,
            action="refused",
            members=previews,
            forced=False,
            dry_run=dry_run,
        )

    if dry_run:
        # Re-plan with the user's actual force value so member outcomes reflect
        # what `rm --force` (vs default rm) would do.
        planned = [rm_workspace(m, config, force=force, dry_run=True) for m in members]
        member_paths_fully_removed = {
            m.root.resolve(strict=False)
            for m, o in zip(members, planned, strict=False)
            if o.action == "would_remove"
        }
        planned_preserved = _enumerate_set_preserved(
            location.root, fully_removed=member_paths_fully_removed
        )
        planned_action: SetRmActionType = "partial" if planned_preserved else "would_remove"
        return SetRmOutcome(
            set_name=set_manifest.name,
            set_path=location.root,
            action=planned_action,
            members=planned,
            preserved=planned_preserved,
            forced=force,
            dry_run=True,
        )

    # Real execution. Archive the whole set first if --force; if archiving
    # fails, abort before touching any member.
    archive_path: Path | None = None
    if force:
        archive_path = archive_or_raise(location.root, set_manifest.name)

    # Now remove each member without re-archiving — the set tarball already
    # captured every member's contents.
    member_outcomes = [
        rm_workspace(
            m,
            config,
            force=force,
            dry_run=False,
            skip_archive=True,
        )
        for m in members
    ]

    # Apply the safety contract at the set root.
    preserved = _enumerate_set_preserved(location.root, fully_removed=set())
    outcome_action: SetRmActionType
    if preserved:
        outcome_action = "partial"
    else:
        set_marker = location.root / SET_MARKER
        if set_marker.is_file():
            try:
                set_marker.unlink()
            except OSError:
                preserved = _enumerate_set_preserved(location.root, fully_removed=set())
        if not preserved and location.root.exists():
            try:
                location.root.rmdir()
                outcome_action = "removed"
            except OSError:
                preserved = _enumerate_set_preserved(location.root, fully_removed=set())
                outcome_action = "partial"
        else:
            outcome_action = "partial" if preserved else "removed"

    return SetRmOutcome(
        set_name=set_manifest.name,
        set_path=location.root,
        action=outcome_action,
        members=member_outcomes,
        preserved=preserved,
        archive_path=archive_path,
        forced=force,
    )


def _enumerate_set_preserved(set_root: Path, *, fully_removed: set[Path]) -> list[Path]:
    """Direct children of ``set_root`` that survive after member removal.

    ``brunch-set.toml`` is the only set-owned marker and is excluded. Member
    directories that have been (or would be, in dry-run) fully removed are
    excluded too; partial members reappear here because their dirs still
    exist after their own ``rm`` returned ``partial``.
    """

    preserved: list[Path] = []
    if not set_root.is_dir():
        return preserved
    try:
        with os.scandir(set_root) as it:
            entries = sorted(it, key=lambda e: e.name)
    except OSError:
        return preserved
    for entry in entries:
        if entry.name == SET_MARKER:
            continue
        path = Path(entry.path)
        try:
            resolved = path.resolve(strict=False)
        except OSError:
            resolved = path
        if resolved in fully_removed:
            continue
        preserved.append(path)
    return preserved
