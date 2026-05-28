from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from brunch.errors import TargetExistsError, TemplateError
from brunch.manifest import load_set_manifest, load_workspace_manifest
from brunch.models import ToolConfig
from brunch.services.init import init_set, init_workspace


def _install_canonical(
    make_canonical: Callable[..., Path], canonical_root: Path, *, name: str
) -> Path:
    target = canonical_root / "github.com" / "kybernetix" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(make_canonical(name)), str(target))
    return target


def _config(root: Path) -> ToolConfig:
    return ToolConfig(root=root, default_forge="github.com")


def _install_template(home: Path, template_id: str, body: str) -> None:
    target = home / ".config" / "brunch" / "templates"
    target.mkdir(parents=True, exist_ok=True)
    (target / f"{template_id}.toml").write_text(body, encoding="utf-8")


class TestInitWorkspace:
    def test_creates_dir_and_manifest(self, tmp_path: Path) -> None:
        target = tmp_path / "task-1"
        outcome = init_workspace(target, name="task-1", config=ToolConfig())
        assert outcome.path == target
        assert outcome.mode == "workspace"
        assert outcome.template_id is None
        assert outcome.sync_report is None
        m = load_workspace_manifest(target / "brunch.toml")
        assert m.name == "task-1"
        assert m.repos == []

    def test_dry_run_does_not_create_anything(self, tmp_path: Path) -> None:
        target = tmp_path / "task-1"
        outcome = init_workspace(target, name="task-1", config=ToolConfig(), dry_run=True)
        assert outcome.dry_run is True
        assert not target.exists()

    def test_existing_target_refused(self, tmp_path: Path) -> None:
        target = tmp_path / "task-1"
        target.mkdir()
        with pytest.raises(TargetExistsError):
            init_workspace(target, name="task-1", config=ToolConfig())

    def test_template_materialises_and_syncs(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        _install_canonical(make_canonical, canonical_root, name="api")
        _install_canonical(make_canonical, canonical_root, name="dashboard")
        _install_template(
            isolated_home,
            "fullstack",
            """
            description = "backend + dashboard"

            [[repo]]
            repo = "kybernetix/api"

            [[repo]]
            repo = "kybernetix/dashboard"
            """,
        )

        target = tmp_path / "task-1"
        outcome = init_workspace(
            target,
            name="task-1",
            config=_config(canonical_root),
            template_id="fullstack",
        )
        assert outcome.template_id == "fullstack"
        assert outcome.sync_report is not None
        assert not outcome.sync_report.has_errors
        # Both worktrees materialised on the workspace-name branch.
        assert (target / "api" / ".git").exists()
        assert (target / "dashboard" / ".git").exists()
        m = load_workspace_manifest(target / "brunch.toml")
        assert len(m.repos) == 2
        assert all(r.branch == "task-1" for r in m.repos)

    def test_missing_template_propagates_error(self, tmp_path: Path, isolated_home: Path) -> None:
        target = tmp_path / "task-1"
        with pytest.raises(TemplateError, match="not found"):
            init_workspace(
                target,
                name="task-1",
                config=ToolConfig(),
                template_id="nonexistent",
            )
        # Target dir was not created either.
        assert not target.exists()


class TestInitSet:
    def test_creates_dir_and_set_manifest(self, tmp_path: Path) -> None:
        target = tmp_path / "set-1"
        outcome = init_set(target, name="set-1")
        assert outcome.mode == "set"
        m = load_set_manifest(target / "brunch-set.toml")
        assert m.name == "set-1"

    def test_dry_run_does_not_create(self, tmp_path: Path) -> None:
        target = tmp_path / "set-1"
        outcome = init_set(target, name="set-1", dry_run=True)
        assert outcome.dry_run is True
        assert not target.exists()

    def test_existing_target_refused(self, tmp_path: Path) -> None:
        target = tmp_path / "set-1"
        target.mkdir()
        with pytest.raises(TargetExistsError):
            init_set(target, name="set-1")
