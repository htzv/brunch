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
from brunch.schema import CURRENT_SCHEMA_VERSION, SCHEMA_VERSION_KEY
from brunch.website import UPDATE_DOCS_URL


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


def _reject_newer_schema(raw: dict[str, object], path: Path) -> None:
    """Refuse a file written by a newer brunch before validating its keys.

    A newer file may have keys this brunch has never heard of, so validating it
    would report those keys as errors instead of the real cause.
    """

    version = raw.get(SCHEMA_VERSION_KEY)
    if isinstance(version, int) and not isinstance(version, bool):
        if version > CURRENT_SCHEMA_VERSION:
            raise ManifestError(
                f"{path} was written by a newer brunch "
                f"(file schema {version}, this brunch supports {CURRENT_SCHEMA_VERSION})",
                hint=f"Update brunch: {UPDATE_DOCS_URL}",
            )


def _describe(error: ValidationError) -> str:
    """One line per problem: ``key: message``."""

    return "\n".join(
        f"  {'.'.join(str(part) for part in problem['loc']) or '(file)'}: {problem['msg']}"
        for problem in error.errors(include_url=False)
    )


def load_workspace_manifest(path: Path) -> WorkspaceManifest:
    """Load and validate a workspace manifest (``brunch.toml``)."""

    raw = _load_toml(path)
    _reject_newer_schema(raw, path)
    try:
        return WorkspaceManifest.model_validate(raw)
    except ValidationError as e:
        raise ManifestError(
            f"invalid workspace manifest at {path}:\n{_describe(e)}",
            hint="See docs/initial-design.md §4.1 for the schema.",
        ) from e


def load_set_manifest(path: Path) -> SetManifest:
    """Load and validate a set manifest (``brunch-set.toml``)."""

    raw = _load_toml(path)
    _reject_newer_schema(raw, path)
    try:
        return SetManifest.model_validate(raw)
    except ValidationError as e:
        raise ManifestError(
            f"invalid set manifest at {path}:\n{_describe(e)}",
            hint="See docs/initial-design.md §4.2 for the schema.",
        ) from e


def write_workspace_manifest(path: Path, manifest: WorkspaceManifest) -> None:
    """Serialize a workspace manifest back to TOML.

    Uses the model's alias (`repo`) for the list of repo entries so the
    round-trip matches the spec in §4.1.
    """

    data: dict[str, object] = {
        SCHEMA_VERSION_KEY: CURRENT_SCHEMA_VERSION,
        "name": manifest.name,
    }
    if manifest.description is not None:
        data["description"] = manifest.description
    if manifest.repos:
        data["repo"] = [r.model_dump(exclude_none=True) for r in manifest.repos]
    if manifest.agents:
        data["agent"] = [a.model_dump(exclude_none=True) for a in manifest.agents]
    path.write_text(tomli_w.dumps(data), encoding="utf-8")


def write_set_manifest(path: Path, manifest: SetManifest) -> None:
    """Serialize a set manifest back to TOML."""

    data: dict[str, object] = {
        SCHEMA_VERSION_KEY: CURRENT_SCHEMA_VERSION,
        "name": manifest.name,
    }
    if manifest.description is not None:
        data["description"] = manifest.description
    path.write_text(tomli_w.dumps(data), encoding="utf-8")
