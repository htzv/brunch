"""Opt-in gate for experimental / potentially-dangerous features.

A feature guarded by :func:`require` runs only when the user opted in via the
top-level ``--enable-experimental=<name>[,<name>…]`` flag (or the
``BRUNCH_ENABLE_EXPERIMENTAL`` env var). Without opt-in the feature refuses to
run and prints a loud warning — so a destructive, storage-format-dependent
operation can never fire by accident.
"""

from __future__ import annotations

import os

import typer

from brunch.errors import BrunchError

#: feature name → one-line description of what it does / why it is risky.
KNOWN: dict[str, str] = {
    "agent-rm": (
        "delete recorded agent conversations, including purging the underlying "
        "session from Claude Code / OpenCode on-disk storage"
    ),
}

ENV_VAR = "BRUNCH_ENABLE_EXPERIMENTAL"

_enabled: set[str] = set()


def _split(raw: str | None) -> set[str]:
    return {p.strip() for p in (raw or "").split(",") if p.strip()}


def set_enabled(raw: str | None) -> None:
    """Populate the enabled set from the CLI flag + env var. Raises on unknown names."""

    global _enabled
    features = _split(raw) | _split(os.environ.get(ENV_VAR))
    unknown = features - set(KNOWN)
    if unknown:
        raise BrunchError(
            f"unknown experimental feature(s): {', '.join(sorted(unknown))}",
            hint=f"known: {', '.join(sorted(KNOWN)) or '(none)'}.",
        )
    _enabled = features


def is_enabled(feature: str) -> bool:
    return feature in _enabled


def require(feature: str) -> None:
    """Refuse (loudly, to stderr) unless ``feature`` was explicitly enabled.

    Raises ``typer.Exit(2)`` after printing the warning, so the command stops
    without taking any action and returns a distinct non-zero code.
    """

    if feature in _enabled:
        return
    desc = KNOWN.get(feature, "this experimental feature")
    typer.secho(
        f"\n  ⚠  EXPERIMENTAL — POSSIBLE DATA LOSS: {feature}",
        err=True,
        fg=typer.colors.RED,
        bold=True,
    )
    typer.secho(
        f"  '{feature}' can {desc}.\n"
        "  It relies on coding-agent storage internals that can change between\n"
        "  releases and may destroy conversation state that cannot be recovered.",
        err=True,
        fg=typer.colors.YELLOW,
    )
    typer.secho(
        f"  Opt in explicitly to proceed:\n"
        f"      br --enable-experimental={feature} <command> …\n"
        f"  (or export {ENV_VAR}={feature})\n",
        err=True,
        fg=typer.colors.BLUE,
    )
    raise typer.Exit(code=2)
