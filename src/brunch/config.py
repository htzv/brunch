"""Tool configuration loading.

Reads ``~/.config/brunch/config.toml`` (or the XDG equivalent on other
platforms) into a validated ``ToolConfig`` model. Missing file → defaults.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import platformdirs
from pydantic import ValidationError

from brunch.errors import ConfigError
from brunch.models import ToolConfig

CONFIG_FILENAME = "config.toml"


def user_config_dir() -> Path:
    """The directory brunch stores user configuration in (XDG-aware)."""

    return Path(platformdirs.user_config_dir("brunch"))


def user_data_dir() -> Path:
    """The directory brunch stores user data in (XDG-aware)."""

    return Path(platformdirs.user_data_dir("brunch"))


def default_config_path() -> Path:
    """The expected location of the config file."""

    return user_config_dir() / CONFIG_FILENAME


def load_config(path: Path | None = None) -> ToolConfig:
    """Load tool config. Returns defaults if the file does not exist.

    Raises ``ConfigError`` on parse or validation failure.
    """

    target = path if path is not None else default_config_path()
    if not target.is_file():
        return ToolConfig()

    try:
        raw = tomllib.loads(target.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(
            f"failed to parse {target}: {e}",
            hint="Check the file for TOML syntax errors.",
        ) from e
    except OSError as e:
        raise ConfigError(f"failed to read {target}: {e}") from e

    try:
        return ToolConfig.model_validate(raw)
    except ValidationError as e:
        raise ConfigError(
            f"invalid configuration in {target}: {e}",
            hint="See `brunch --help` and docs/initial-design.md §4.3 for valid keys.",
        ) from e
