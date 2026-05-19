"""Workspace template discovery and materialisation.

Templates are partial workspace manifests stored at
``~/.config/brunch/templates/<id>.toml``. They differ from a real
``brunch.toml`` only in two ways:

1. ``name`` is optional (it gets filled in at materialisation time from the
   ``brunch init <name>`` argument);
2. each ``[[repo]]`` entry may omit ``branch`` (defaulted to the workspace
   name) and ``base`` (defaulted to ``"main"``).

There is deliberately no ``brunch templates list/show/copy`` UX in v1 —
templates are files in a known directory; ``ls`` is the discovery tool.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import ValidationError

from brunch.config import user_config_dir
from brunch.errors import TemplateError
from brunch.models import WorkspaceManifest

TEMPLATE_DEFAULT_BASE = "main"


def template_dir() -> Path:
    """Directory where user-installed templates live."""

    return user_config_dir() / "templates"


def template_path(template_id: str) -> Path:
    """Expected path of a given template id."""

    return template_dir() / f"{template_id}.toml"


def materialise_template(template_id: str, *, workspace_name: str) -> WorkspaceManifest:
    """Load a template by id and turn it into a full WorkspaceManifest.

    Applies the documented defaults: ``name`` is forced to ``workspace_name``;
    each repo entry's ``branch`` falls back to ``workspace_name``; each repo
    entry's ``base`` falls back to ``"main"``.
    """

    path = template_path(template_id)
    if not path.is_file():
        raise TemplateError(
            f"template {template_id!r} not found at {path}",
            hint=(f"create the file, or list available templates with `ls {template_dir()}`."),
        )

    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise TemplateError(
            f"failed to parse template {path}: {e}",
            hint="Check the file for TOML syntax errors.",
        ) from e
    except OSError as e:
        raise TemplateError(f"failed to read template {path}: {e}") from e

    if not isinstance(raw, dict):
        raise TemplateError(f"template {path} did not parse to a TOML table")

    # Override any name in the template; the workspace name is authoritative.
    raw["name"] = workspace_name

    repos = raw.get("repo")
    if repos is not None:
        if not isinstance(repos, list):
            raise TemplateError(
                f"template {path}: `repo` must be an array of tables",
                hint="See docs/initial-design.md §5 for the shape.",
            )
        for r in repos:
            if not isinstance(r, dict):
                raise TemplateError(f"template {path}: each [[repo]] entry must be a table")
            r.setdefault("branch", workspace_name)
            r.setdefault("base", TEMPLATE_DEFAULT_BASE)

    try:
        return WorkspaceManifest.model_validate(raw)
    except ValidationError as e:
        raise TemplateError(
            f"template {path} does not match the manifest schema: {e}",
            hint="See docs/initial-design.md §4.1 for required fields.",
        ) from e
