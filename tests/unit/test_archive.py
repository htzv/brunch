from __future__ import annotations

import tarfile
from datetime import UTC, datetime
from pathlib import Path

from brunch.archive import (
    archive_filename,
    create_workspace_archive,
)


class TestArchiveFilename:
    def test_includes_workspace_name_and_utc_stamp(self) -> None:
        when = datetime(2026, 5, 20, 9, 30, 0, tzinfo=UTC)
        assert archive_filename("task-1234", when=when) == "task-1234-20260520T093000Z.tar.gz"

    def test_default_now_uses_utc(self) -> None:
        name = archive_filename("ws")
        assert name.startswith("ws-")
        assert name.endswith("Z.tar.gz")


class TestDefaultArchiveDir:
    def test_under_user_data_dir(self, isolated_home: Path) -> None:
        from importlib import reload

        import brunch.archive as arch_module
        import brunch.config as cfg_module

        reload(cfg_module)
        reload(arch_module)
        path = arch_module.default_archive_dir()
        assert path.name == "archives"
        assert "brunch" in path.parts


class TestCreateWorkspaceArchive:
    def test_creates_tarball_under_named_root(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws-1"
        workspace.mkdir()
        (workspace / "brunch.toml").write_text('name = "ws-1"\n', encoding="utf-8")
        (workspace / "api").mkdir()
        (workspace / "api" / "README.md").write_text("# api\n", encoding="utf-8")

        archive_dir = tmp_path / "archives"
        when = datetime(2026, 5, 20, 9, 30, 0, tzinfo=UTC)
        archive_path = create_workspace_archive(
            workspace,
            workspace_name="ws-1",
            archive_dir=archive_dir,
            when=when,
        )
        assert archive_path == archive_dir / "ws-1-20260520T093000Z.tar.gz"
        assert archive_path.is_file()

        with tarfile.open(archive_path) as tar:
            names = tar.getnames()
        assert "ws-1/brunch.toml" in names
        assert "ws-1/api/README.md" in names

    def test_round_trip_restores_contents(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws-1"
        workspace.mkdir()
        (workspace / "brunch.toml").write_text('name = "ws-1"\n', encoding="utf-8")
        (workspace / "marker.txt").write_text("hello\n", encoding="utf-8")

        archive_path = create_workspace_archive(
            workspace, workspace_name="ws-1", archive_dir=tmp_path / "archives"
        )

        extract_to = tmp_path / "extracted"
        extract_to.mkdir()
        with tarfile.open(archive_path) as tar:
            tar.extractall(extract_to)
        assert (extract_to / "ws-1" / "marker.txt").read_text() == "hello\n"

    def test_creates_archive_dir_if_missing(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws-1"
        workspace.mkdir()
        (workspace / "brunch.toml").write_text('name = "ws-1"\n', encoding="utf-8")

        nested = tmp_path / "a" / "b" / "c"
        assert not nested.exists()
        archive_path = create_workspace_archive(
            workspace, workspace_name="ws-1", archive_dir=nested
        )
        assert archive_path.parent == nested
        assert nested.is_dir()
