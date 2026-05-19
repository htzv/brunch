"""Manifest reading and writing.

`brunch.toml` (workspace) and `brunch-set.toml` (set) are the on-disk
authoritative description of a workspace or set. This module is the only
place that knows their TOML shape.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import tomli_w
from pydantic import ValidationError

from brunch.errors import ManifestError
from brunch.models import SetManifest, WorkspaceManifest


def _load_toml(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise ManifestError(f"manifest not found: {path}")
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise ManifestError(
            f"failed to parse {path}: {e}",
            hint="Check the file for TOML syntax errors.",
        ) from e
    except OSError as e:
        raise ManifestError(f"failed to read {path}: {e}") from e


def load_workspace_manifest(path: Path) -> WorkspaceManifest:
    """Load and validate a workspace manifest (``brunch.toml``)."""

    raw = _load_toml(path)
    try:
        return WorkspaceManifest.model_validate(raw)
    except ValidationError as e:
        raise ManifestError(
            f"invalid workspace manifest at {path}: {e}",
            hint="See docs/initial-design.md §4.1 for the schema.",
        ) from e


def load_set_manifest(path: Path) -> SetManifest:
    """Load and validate a set manifest (``brunch-set.toml``)."""

    raw = _load_toml(path)
    try:
        return SetManifest.model_validate(raw)
    except ValidationError as e:
        raise ManifestError(
            f"invalid set manifest at {path}: {e}",
            hint="See docs/initial-design.md §4.2 for the schema.",
        ) from e


def write_workspace_manifest(path: Path, manifest: WorkspaceManifest) -> None:
    """Serialize a workspace manifest back to TOML.

    Uses the model's alias (`repo`) for the list of repo entries so the
    round-trip matches the spec in §4.1.
    """

    data: dict[str, object] = {"name": manifest.name}
    if manifest.description is not None:
        data["description"] = manifest.description
    if manifest.repos:
        data["repo"] = [r.model_dump(exclude_none=True) for r in manifest.repos]
    path.write_text(tomli_w.dumps(data), encoding="utf-8")


def write_set_manifest(path: Path, manifest: SetManifest) -> None:
    """Serialize a set manifest back to TOML."""

    data: dict[str, object] = {"name": manifest.name}
    if manifest.description is not None:
        data["description"] = manifest.description
    path.write_text(tomli_w.dumps(data), encoding="utf-8")
