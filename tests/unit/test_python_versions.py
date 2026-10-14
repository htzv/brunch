"""The Python versions CI tests are the ones pyproject.toml claims to support."""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CLASSIFIER_PREFIX = "Programming Language :: Python :: 3."


def test_tested_versions_match_the_classifiers() -> None:
    tested = (REPO_ROOT / "scripts" / "python-versions.txt").read_text().split()
    classifiers = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())["project"][
        "classifiers"
    ]
    claimed = [
        "3." + c.removeprefix(CLASSIFIER_PREFIX)
        for c in classifiers
        if c.startswith(CLASSIFIER_PREFIX)
    ]
    assert tested == claimed
