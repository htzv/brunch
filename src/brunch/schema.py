"""Version of the on-disk manifest format.

One number covers both ``brunch.toml`` and ``brunch-set.toml``. A file without
``schema_version`` was written before versions existed (version 1 or 2, which
read the same) and is read as the current version.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

# TODO: document how to introduce a new schema version and keep reading older
# ones. Brunch has no migrations yet.
SCHEMA_VERSION_KEY = "schema_version"
OLDEST_SCHEMA_VERSION = 1
CURRENT_SCHEMA_VERSION = 2

SchemaVersion = Annotated[
    int,
    Field(strict=True, ge=OLDEST_SCHEMA_VERSION, le=CURRENT_SCHEMA_VERSION),
]
