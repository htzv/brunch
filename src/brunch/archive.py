"""Tarball archives for `brunch rm --force`.

The archive policy is the "fat" variant from ``docs/initial-design.md
§7.5``: a tar.gz of the entire workspace directory, including each
repo's worktree contents (which themselves reference back to the
canonical clone via the worktree's ``.git`` file).

Restoring an archive is iteration-2 territory (`brunch restore`); for
now the archive is a safety net the user can untar by hand if anything
was lost.
"""

from __future__ import annotations

import tarfile
from datetime import UTC, datetime
from pathlib import Path

from brunch.config import user_data_dir


def default_archive_dir() -> Path:
    """The directory ``brunch rm --force`` writes archives to by default."""

    return user_data_dir() / "archives"


def archive_filename(workspace_name: str, *, when: datetime | None = None) -> str:
    """Compose the conventional archive filename for ``workspace_name``."""

    moment = when or datetime.now(UTC)
    stamp = moment.strftime("%Y%m%dT%H%M%SZ")
    return f"{workspace_name}-{stamp}.tar.gz"


def create_workspace_archive(
    workspace_path: Path,
    *,
    workspace_name: str,
    archive_dir: Path | None = None,
    when: datetime | None = None,
) -> Path:
    """Create a tar.gz archive of ``workspace_path``.

    The archive is written to ``<archive_dir>/<workspace_name>-<UTC>.tar.gz``
    (default ``archive_dir``: ``~/.local/share/brunch/archives/``). The
    workspace's contents are stored under the top-level directory
    ``<workspace_name>/`` inside the tar.
    """

    target_dir = archive_dir if archive_dir is not None else default_archive_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    archive_path = target_dir / archive_filename(workspace_name, when=when)

    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(str(workspace_path), arcname=workspace_name)
    return archive_path
