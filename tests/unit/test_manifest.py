from __future__ import annotations

from pathlib import Path

import pytest

from brunch.errors import ManifestError
from brunch.manifest import (
    load_set_manifest,
    load_workspace_manifest,
    write_set_manifest,
    write_workspace_manifest,
)
from brunch.models import RepoEntry, SetManifest, WorkspaceManifest

WORKSPACE_TOML = """\
name = "task-1234"
description = "Test workspace."

[[repo]]
repo = "kybernetix/api"
branch = "task-1234"
base = "main"

[[repo]]
repo = "github.com/kybernetix/dashboard"
branch = "task-1234"
base = "main"
"""

SET_TOML = """\
name = "2026-Q2_x"
description = "Set description."
"""


class TestLoadWorkspaceManifest:
    def test_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "brunch.toml"
        path.write_text(WORKSPACE_TOML, encoding="utf-8")
        m = load_workspace_manifest(path)
        assert m.name == "task-1234"
        assert m.description == "Test workspace."
        assert len(m.repos) == 2
        assert m.repos[0] == RepoEntry(repo="kybernetix/api", branch="task-1234", base="main")
        assert m.repos[1].repo == "github.com/kybernetix/dashboard"

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(ManifestError, match="not found"):
            load_workspace_manifest(tmp_path / "missing.toml")

    def test_invalid_toml(self, tmp_path: Path) -> None:
        path = tmp_path / "brunch.toml"
        path.write_text("not = valid = toml", encoding="utf-8")
        with pytest.raises(ManifestError, match="failed to parse"):
            load_workspace_manifest(path)

    def test_missing_required_fields(self, tmp_path: Path) -> None:
        path = tmp_path / "brunch.toml"
        path.write_text('name = "x"\n[[repo]]\nrepo = "kybernetix/api"\n', encoding="utf-8")
        with pytest.raises(ManifestError, match="invalid workspace manifest"):
            load_workspace_manifest(path)

    def test_unknown_top_level_field_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "brunch.toml"
        path.write_text('name = "x"\nmystery = "y"\n', encoding="utf-8")
        with pytest.raises(ManifestError, match="invalid workspace manifest"):
            load_workspace_manifest(path)

    def test_unknown_repo_field_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "brunch.toml"
        path.write_text(
            'name = "x"\n[[repo]]\nrepo = "a/b"\nbranch = "b"\nbase = "main"\nmystery = "y"\n',
            encoding="utf-8",
        )
        with pytest.raises(ManifestError):
            load_workspace_manifest(path)

    def test_workspace_with_no_repos_is_valid(self, tmp_path: Path) -> None:
        path = tmp_path / "brunch.toml"
        path.write_text('name = "x"\n', encoding="utf-8")
        m = load_workspace_manifest(path)
        assert m.repos == []


class TestLoadSetManifest:
    def test_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "brunch-set.toml"
        path.write_text(SET_TOML, encoding="utf-8")
        m = load_set_manifest(path)
        assert m.name == "2026-Q2_x"
        assert m.description == "Set description."

    def test_missing_name_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "brunch-set.toml"
        path.write_text('description = "x"\n', encoding="utf-8")
        with pytest.raises(ManifestError):
            load_set_manifest(path)


class TestWriteWorkspaceManifest:
    def test_round_trip_through_write(self, tmp_path: Path) -> None:
        m = WorkspaceManifest(
            name="t",
            description="d",
            repo=[RepoEntry(repo="kybernetix/api", branch="t", base="main")],
        )
        path = tmp_path / "brunch.toml"
        write_workspace_manifest(path, m)
        roundtrip = load_workspace_manifest(path)
        assert roundtrip == m

    def test_omits_description_if_none(self, tmp_path: Path) -> None:
        m = WorkspaceManifest(name="t")
        path = tmp_path / "brunch.toml"
        write_workspace_manifest(path, m)
        text = path.read_text(encoding="utf-8")
        assert "description" not in text


class TestWriteSetManifest:
    def test_round_trip(self, tmp_path: Path) -> None:
        m = SetManifest(name="s", description="d")
        path = tmp_path / "brunch-set.toml"
        write_set_manifest(path, m)
        assert load_set_manifest(path) == m
