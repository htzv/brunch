from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from brunch.errors import WorkspaceNotFoundError
from brunch.models import ToolConfig, WorkspaceLocation
from brunch.services.status import compute_workspace_status


def _workspace_with(
    ws: Path,
    *,
    description: str | None = None,
    repos: list[tuple[str, str, str]] | None = None,
) -> WorkspaceLocation:
    manifest_path = ws / "brunch.toml"
    content = f'name = "{ws.name}"\n'
    if description is not None:
        content += f'description = "{description}"\n'
    for repo, branch, base in repos or []:
        content += f'\n[[repo]]\nrepo = "{repo}"\nbranch = "{branch}"\nbase = "{base}"\n'
    manifest_path.write_text(content, encoding="utf-8")
    return WorkspaceLocation(mode="workspace", root=ws, manifest_path=manifest_path)


class TestComputeWorkspaceStatus:
    def test_workspace_with_no_repos(self, make_workspace: Callable[..., Path]) -> None:
        ws = make_workspace("empty-ws")
        loc = _workspace_with(ws, description="d")
        result = compute_workspace_status(loc, ToolConfig())
        assert result.workspace_name == "empty-ws"
        assert result.description == "d"
        assert result.repos == []

    def test_missing_worktree_marked_not_exists(self, make_workspace: Callable[..., Path]) -> None:
        ws = make_workspace("ws1")
        loc = _workspace_with(ws, repos=[("kybernetix/api", "feat", "main")])
        result = compute_workspace_status(loc, ToolConfig())
        assert len(result.repos) == 1
        r = result.repos[0]
        assert r.exists is False
        assert r.short_name == "api"
        assert r.declared_branch == "feat"
        assert r.declared_base == "main"
        assert r.current_branch is None
        assert r.on_declared_branch is False

    def test_existing_worktree_clean(
        self,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        canonical = make_canonical("api")
        ws = make_workspace("ws1")
        worktree_factory(canonical, ws / "api", branch="feat", base="main")
        loc = _workspace_with(ws, repos=[("kybernetix/api", "feat", "main")])
        result = compute_workspace_status(loc, ToolConfig())
        r = result.repos[0]
        assert r.exists is True
        assert r.current_branch == "feat"
        assert r.on_declared_branch is True
        assert r.has_uncommitted is False
        assert r.has_untracked is False

    def test_existing_worktree_with_uncommitted(
        self,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        canonical = make_canonical("api")
        ws = make_workspace("ws1")
        worktree_factory(canonical, ws / "api", branch="feat", base="main")
        (ws / "api" / "README.md").write_text("dirty\n", encoding="utf-8")
        loc = _workspace_with(ws, repos=[("kybernetix/api", "feat", "main")])
        r = compute_workspace_status(loc, ToolConfig()).repos[0]
        assert r.has_uncommitted is True

    def test_drift_when_branch_differs_from_manifest(
        self,
        make_canonical: Callable[..., Path],
        make_workspace: Callable[..., Path],
        worktree_factory: Callable[..., None],
    ) -> None:
        canonical = make_canonical("api")
        ws = make_workspace("ws1")
        worktree_factory(canonical, ws / "api", branch="actual", base="main")
        loc = _workspace_with(ws, repos=[("kybernetix/api", "declared", "main")])
        r = compute_workspace_status(loc, ToolConfig()).repos[0]
        assert r.current_branch == "actual"
        assert r.declared_branch == "declared"
        assert r.on_declared_branch is False

    def test_set_mode_rejected_in_m1(self, tmp_path: Path) -> None:
        marker = tmp_path / "brunch-set.toml"
        marker.write_text('name = "s"\n', encoding="utf-8")
        loc = WorkspaceLocation(mode="set", root=tmp_path, manifest_path=marker)
        with pytest.raises(WorkspaceNotFoundError, match="set roots"):
            compute_workspace_status(loc, ToolConfig())
