"""Path resolution and walk-up discovery.

Pure functions — no I/O beyond filesystem existence checks. These are the
geometric primitives the service layer composes on top of.
"""

from __future__ import annotations

import os
from pathlib import Path

from brunch.errors import RepoSpecError, WorkspaceNotFoundError
from brunch.models import RepoSpec, WorkspaceLocation

WORKSPACE_MARKER = "brunch.toml"
SET_MARKER = "brunch-set.toml"


def parse_repo_spec(raw: str, *, default_forge: str) -> RepoSpec:
    """Parse a repo spec string into a fully-qualified RepoSpec.

    Accepts either the short form (``<org>/<name>``, forge inferred from
    ``default_forge``) or the long form (``<forge>/<org>/<name>``). Empty
    segments or extra/fewer slashes are rejected.
    """

    if not raw or raw.strip() != raw:
        raise RepoSpecError(
            f"repo spec must be a non-empty trimmed string (got {raw!r})",
            hint="Use the form 'kybernetix/api' or 'github.com/kybernetix/api'.",
        )

    parts = raw.split("/")
    if any(not p for p in parts):
        raise RepoSpecError(
            f"repo spec {raw!r} has empty segments",
            hint="Use the form 'kybernetix/api' or 'github.com/kybernetix/api'.",
        )

    if len(parts) == 2:
        org, name = parts
        forge = default_forge
    elif len(parts) == 3:
        forge, org, name = parts
    else:
        raise RepoSpecError(
            f"repo spec {raw!r} has {len(parts)} segments, expected 2 or 3",
            hint="Use the form 'kybernetix/api' or 'github.com/kybernetix/api'.",
        )

    return RepoSpec(forge=forge, org=org, name=name)


def expand_root(root: Path) -> Path:
    """Expand ``~`` and environment variables in a configured root path."""

    return Path(os.path.expandvars(str(root))).expanduser()


def canonical_clone_path(spec: RepoSpec, *, root: Path) -> Path:
    """Compute the ghq-style canonical clone path for a repo spec.

    Layout: ``<root>/<forge>/<org>/<name>``.
    """

    return expand_root(root) / spec.forge / spec.org / spec.name


def discover_set_members(set_root: Path) -> list[WorkspaceLocation]:
    """Return direct child workspaces of ``set_root``.

    A child is considered a member if it is a direct subdirectory that
    contains a ``brunch.toml`` marker. Symlinks are not followed. Results
    are sorted by directory name so callers get stable ordering.
    """

    members: list[WorkspaceLocation] = []
    if not set_root.is_dir():
        return members

    try:
        with os.scandir(set_root) as it:
            entries = sorted(it, key=lambda e: e.name)
    except OSError:
        return members

    for entry in entries:
        try:
            if not entry.is_dir(follow_symlinks=False):
                continue
        except OSError:
            continue
        child = Path(entry.path)
        manifest_path = child / WORKSPACE_MARKER
        if manifest_path.is_file():
            members.append(
                WorkspaceLocation(
                    mode="workspace",
                    root=child,
                    manifest_path=manifest_path,
                )
            )
    return members


def discover_workspace(start: Path) -> WorkspaceLocation:
    """Walk up from ``start`` looking for a workspace or set marker.

    Returns the first marker found. If both markers coexist at the same
    level, that's an ambiguous configuration and we raise. If neither is
    found before the filesystem root, raise ``WorkspaceNotFoundError``.
    """

    current = start.resolve()
    while True:
        ws = current / WORKSPACE_MARKER
        ss = current / SET_MARKER
        ws_exists = ws.is_file()
        ss_exists = ss.is_file()

        if ws_exists and ss_exists:
            raise WorkspaceNotFoundError(
                f"both {WORKSPACE_MARKER} and {SET_MARKER} found at {current}",
                hint="A directory should have at most one brunch marker file.",
            )
        if ws_exists:
            return WorkspaceLocation(mode="workspace", root=current, manifest_path=ws)
        if ss_exists:
            return WorkspaceLocation(mode="set", root=current, manifest_path=ss)

        if current.parent == current:
            raise WorkspaceNotFoundError(
                f"no {WORKSPACE_MARKER} or {SET_MARKER} found in {start} or any parent",
                hint=(
                    "cd into a workspace/set, or create one with `brunch init`. "
                    "Use `-w <path>` to point brunch at a specific directory."
                ),
            )
        current = current.parent
