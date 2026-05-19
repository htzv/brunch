"""Service: create new workspaces and workspace sets."""

from __future__ import annotations

from pathlib import Path

from brunch.errors import TargetExistsError
from brunch.manifest import write_set_manifest, write_workspace_manifest
from brunch.models import (
    InitOutcome,
    SetManifest,
    SyncReport,
    ToolConfig,
    WorkspaceLocation,
    WorkspaceManifest,
)
from brunch.services.sync import sync_workspace
from brunch.templates import materialise_template


def init_workspace(
    target: Path,
    *,
    name: str,
    config: ToolConfig,
    template_id: str | None = None,
    dry_run: bool = False,
) -> InitOutcome:
    """Create a workspace directory + ``brunch.toml``.

    With ``template_id`` set, the manifest is built from the template; if it
    declares ``[[repo]]`` entries, ``sync_workspace`` is then invoked to
    materialise the worktrees in one pass.
    """

    _refuse_if_exists(target)

    if template_id is not None:
        manifest = materialise_template(template_id, workspace_name=name)
    else:
        manifest = WorkspaceManifest(name=name)

    sync_report: SyncReport | None = None

    if dry_run:
        return InitOutcome(
            name=name,
            mode="workspace",
            path=target,
            template_id=template_id,
            sync_report=None,
            dry_run=True,
        )

    target.mkdir(parents=True)
    manifest_path = target / "brunch.toml"
    write_workspace_manifest(manifest_path, manifest)

    if manifest.repos:
        location = WorkspaceLocation(mode="workspace", root=target, manifest_path=manifest_path)
        sync_report = sync_workspace(location, config)

    return InitOutcome(
        name=name,
        mode="workspace",
        path=target,
        template_id=template_id,
        sync_report=sync_report,
    )


def init_set(
    target: Path,
    *,
    name: str,
    dry_run: bool = False,
) -> InitOutcome:
    """Create a set directory + ``brunch-set.toml``."""

    _refuse_if_exists(target)

    if dry_run:
        return InitOutcome(name=name, mode="set", path=target, dry_run=True)

    target.mkdir(parents=True)
    write_set_manifest(target / "brunch-set.toml", SetManifest(name=name))
    return InitOutcome(name=name, mode="set", path=target)


def _refuse_if_exists(target: Path) -> None:
    if target.exists():
        raise TargetExistsError(
            f"target {target} already exists",
            hint="pick a different name or remove the directory first.",
        )
