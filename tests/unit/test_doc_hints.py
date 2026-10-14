"""Error hints send people to the published docs, never to repo-only files."""

from __future__ import annotations

from pathlib import Path

import pytest

from brunch.config import load_config
from brunch.errors import BrunchError
from brunch.manifest import load_set_manifest, load_workspace_manifest
from brunch.templates import materialise_template, template_path
from brunch.website import BRUNCH_WEBSITE_URL

INVALID_KEY = 'bogus = 1\nname = "x"\n'


def _hint_of(action: object) -> str:
    with pytest.raises(BrunchError) as caught:
        action()  # type: ignore[operator]
    assert caught.value.hint is not None
    return caught.value.hint


def _write(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    path.write_text(INVALID_KEY, encoding="utf-8")
    return path


def test_workspace_manifest_hint_links_to_the_website(tmp_path: Path) -> None:
    path = _write(tmp_path, "brunch.toml")
    hint = _hint_of(lambda: load_workspace_manifest(path))
    assert f"{BRUNCH_WEBSITE_URL}/" in hint
    assert "docs/initial-design.md" not in hint


def test_set_manifest_hint_links_to_the_website(tmp_path: Path) -> None:
    path = _write(tmp_path, "brunch-set.toml")
    hint = _hint_of(lambda: load_set_manifest(path))
    assert f"{BRUNCH_WEBSITE_URL}/" in hint
    assert "docs/initial-design.md" not in hint


def test_tool_config_hint_links_to_the_website(tmp_path: Path) -> None:
    path = _write(tmp_path, "config.toml")
    hint = _hint_of(lambda: load_config(path))
    assert f"{BRUNCH_WEBSITE_URL}/" in hint
    assert "docs/initial-design.md" not in hint


def test_template_hints_link_to_the_website(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    template = template_path("broken")
    template.parent.mkdir(parents=True)
    template.write_text(INVALID_KEY, encoding="utf-8")
    hint = _hint_of(lambda: materialise_template("broken", workspace_name="w"))
    assert f"{BRUNCH_WEBSITE_URL}/" in hint
    assert "docs/initial-design.md" not in hint
