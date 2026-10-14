"""The manifest format version: written on save, defaulted on read, bounded."""

from __future__ import annotations

from pathlib import Path

import pytest

from brunch.errors import ManifestError
from brunch.manifest import (
    UPDATE_DOCS_URL,
    load_set_manifest,
    load_workspace_manifest,
    write_set_manifest,
    write_workspace_manifest,
)
from brunch.models import SetManifest, WorkspaceManifest
from brunch.schema import CURRENT_SCHEMA_VERSION, OLDEST_SCHEMA_VERSION, SCHEMA_VERSION_KEY

WORKSPACE_FILE_WITHOUT_VERSION = 'name = "demo"\n'
SET_FILE_WITHOUT_VERSION = 'name = "demo-set"\n'
NEWER_THAN_SUPPORTED = CURRENT_SCHEMA_VERSION + 1
BELOW_OLDEST = OLDEST_SCHEMA_VERSION - 1


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "brunch.toml"
    path.write_text(text, encoding="utf-8")
    return path


class TestWriting:
    def test_workspace_manifest_starts_with_the_current_version(self, tmp_path: Path) -> None:
        path = tmp_path / "brunch.toml"
        write_workspace_manifest(path, WorkspaceManifest(name="demo"))
        first_line = path.read_text(encoding="utf-8").splitlines()[0]
        assert first_line == f"{SCHEMA_VERSION_KEY} = {CURRENT_SCHEMA_VERSION}"

    def test_set_manifest_starts_with_the_current_version(self, tmp_path: Path) -> None:
        path = tmp_path / "brunch-set.toml"
        write_set_manifest(path, SetManifest(name="demo-set"))
        first_line = path.read_text(encoding="utf-8").splitlines()[0]
        assert first_line == f"{SCHEMA_VERSION_KEY} = {CURRENT_SCHEMA_VERSION}"

    def test_workspace_manifest_round_trips(self, tmp_path: Path) -> None:
        path = tmp_path / "brunch.toml"
        manifest = WorkspaceManifest(name="demo", description="d")
        write_workspace_manifest(path, manifest)
        assert load_workspace_manifest(path) == manifest

    def test_saving_a_file_that_declared_an_older_version_writes_the_current_one(
        self, tmp_path: Path
    ) -> None:
        path = _write(tmp_path, f"{SCHEMA_VERSION_KEY} = {OLDEST_SCHEMA_VERSION}\nname = 'demo'\n")
        loaded = load_workspace_manifest(path)
        assert loaded.schema_version == OLDEST_SCHEMA_VERSION
        write_workspace_manifest(path, loaded)
        assert load_workspace_manifest(path).schema_version == CURRENT_SCHEMA_VERSION


class TestReading:
    def test_workspace_file_without_a_version_reads_as_current(self, tmp_path: Path) -> None:
        path = _write(tmp_path, WORKSPACE_FILE_WITHOUT_VERSION)
        assert load_workspace_manifest(path).schema_version == CURRENT_SCHEMA_VERSION

    def test_set_file_without_a_version_reads_as_current(self, tmp_path: Path) -> None:
        path = _write(tmp_path, SET_FILE_WITHOUT_VERSION)
        assert load_set_manifest(path).schema_version == CURRENT_SCHEMA_VERSION

    @pytest.mark.parametrize("bad", [NEWER_THAN_SUPPORTED, BELOW_OLDEST, -1])
    def test_version_outside_the_supported_range_is_rejected(
        self, tmp_path: Path, bad: int
    ) -> None:
        path = _write(tmp_path, f"{SCHEMA_VERSION_KEY} = {bad}\nname = 'demo'\n")
        with pytest.raises(ManifestError):
            load_workspace_manifest(path)

    @pytest.mark.parametrize("bad", ['"2"', "2.0", "true"])
    def test_version_that_is_not_an_integer_is_rejected(self, tmp_path: Path, bad: str) -> None:
        path = _write(tmp_path, f"{SCHEMA_VERSION_KEY} = {bad}\nname = 'demo'\n")
        with pytest.raises(ManifestError):
            load_workspace_manifest(path)

    def test_set_version_outside_the_supported_range_is_rejected(self, tmp_path: Path) -> None:
        path = _write(tmp_path, f"{SCHEMA_VERSION_KEY} = {NEWER_THAN_SUPPORTED}\nname = 'demo'\n")
        with pytest.raises(ManifestError):
            load_set_manifest(path)


class TestNewerFile:
    """A file from a newer brunch is named as such, not blamed on its keys."""

    NEWER_FILE_WITH_UNKNOWN_KEY = (
        f"{SCHEMA_VERSION_KEY} = {NEWER_THAN_SUPPORTED}\nname = 'demo'\nfuture_key = 1\n"
    )

    @pytest.mark.parametrize(
        "load, text",
        [
            (load_workspace_manifest, NEWER_FILE_WITH_UNKNOWN_KEY),
            (load_set_manifest, NEWER_FILE_WITH_UNKNOWN_KEY),
        ],
    )
    def test_says_which_versions_are_involved_and_how_to_update(
        self, tmp_path: Path, load: object, text: str
    ) -> None:
        path = _write(tmp_path, text)
        with pytest.raises(ManifestError) as caught:
            load(path)  # type: ignore[operator]
        message = str(caught.value)
        assert str(path) in message
        assert "newer brunch" in message
        assert f"file schema {NEWER_THAN_SUPPORTED}" in message
        assert f"supports {CURRENT_SCHEMA_VERSION}" in message
        assert "unknown" not in message.lower()
        assert caught.value.hint is not None
        assert UPDATE_DOCS_URL in caught.value.hint


class TestUnknownKeyAtSupportedVersion:
    def test_names_the_file_and_the_key_without_pydantic_noise(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path, f"{SCHEMA_VERSION_KEY} = {CURRENT_SCHEMA_VERSION}\nname = 'x'\nbogus = 1\n"
        )
        with pytest.raises(ManifestError) as caught:
            load_workspace_manifest(path)
        message = str(caught.value)
        assert str(path) in message
        assert "bogus: Extra inputs are not permitted" in message
        assert "pydantic.dev" not in message
        assert "validation error" not in message

    def test_nested_keys_are_named_by_path(self, tmp_path: Path) -> None:
        path = _write(tmp_path, 'name = "x"\n[[repo]]\nrepo = "a/b"\nbogus = 1\n')
        with pytest.raises(ManifestError) as caught:
            load_workspace_manifest(path)
        assert "repo.0.bogus" in str(caught.value)
