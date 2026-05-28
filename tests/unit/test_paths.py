from __future__ import annotations

from pathlib import Path

import pytest

from brunch.errors import RepoSpecError, WorkspaceNotFoundError
from brunch.models import RepoSpec
from brunch.paths import (
    SET_MARKER,
    WORKSPACE_MARKER,
    canonical_clone_path,
    discover_set_members,
    discover_workspace,
    expand_root,
    parse_repo_spec,
)


class TestParseRepoSpec:
    def test_short_form_infers_default_forge(self) -> None:
        spec = parse_repo_spec("kybernetix/api", default_forge="github.com")
        assert spec == RepoSpec(forge="github.com", org="kybernetix", name="api")

    def test_long_form_uses_explicit_forge(self) -> None:
        spec = parse_repo_spec("gitlab.internal/team/svc", default_forge="github.com")
        assert spec == RepoSpec(forge="gitlab.internal", org="team", name="svc")

    @pytest.mark.parametrize(
        "bad",
        [
            "",
            " ",
            "  kybernetix/api",
            "kybernetix/api  ",
            "single",
            "a/b/c/d",
            "a//b",
            "/kybernetix/api",
        ],
    )
    def test_rejects_malformed(self, bad: str) -> None:
        with pytest.raises(RepoSpecError):
            parse_repo_spec(bad, default_forge="github.com")


class TestRepoSpecProperties:
    def test_short_and_qualified(self) -> None:
        spec = RepoSpec(forge="github.com", org="kybernetix", name="api")
        assert spec.short == "kybernetix/api"
        assert spec.qualified == "github.com/kybernetix/api"


class TestExpandRoot:
    def test_expands_tilde(self) -> None:
        assert expand_root(Path("~/x")).is_absolute()
        assert str(expand_root(Path("~/x"))).endswith("/x")

    def test_expands_envvar(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BRUNCH_TEST_DIR", "/tmp/brunch-test")
        assert expand_root(Path("$BRUNCH_TEST_DIR/repos")) == Path("/tmp/brunch-test/repos")

    def test_leaves_plain_paths_alone(self) -> None:
        assert expand_root(Path("/var/lib/x")) == Path("/var/lib/x")


class TestCanonicalClonePath:
    def test_layout_is_forge_org_name(self) -> None:
        spec = RepoSpec(forge="github.com", org="kybernetix", name="api")
        assert canonical_clone_path(spec, root=Path("/srv/r")) == Path(
            "/srv/r/github.com/kybernetix/api"
        )

    def test_expands_tilde_in_root(self) -> None:
        spec = RepoSpec(forge="github.com", org="kybernetix", name="api")
        out = canonical_clone_path(spec, root=Path("~/x"))
        assert out.is_absolute()
        assert str(out).endswith("/x/github.com/kybernetix/api")


class TestDiscoverWorkspace:
    def test_finds_workspace_marker_at_cwd(self, tmp_path: Path) -> None:
        (tmp_path / WORKSPACE_MARKER).write_text("name='t'\n")
        loc = discover_workspace(tmp_path)
        assert loc.mode == "workspace"
        assert loc.root == tmp_path.resolve()
        assert loc.manifest_path.name == WORKSPACE_MARKER

    def test_finds_set_marker_at_cwd(self, tmp_path: Path) -> None:
        (tmp_path / SET_MARKER).write_text("name='s'\n")
        loc = discover_workspace(tmp_path)
        assert loc.mode == "set"
        assert loc.manifest_path.name == SET_MARKER

    def test_walks_up_to_find_marker(self, tmp_path: Path) -> None:
        (tmp_path / WORKSPACE_MARKER).write_text("name='t'\n")
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        loc = discover_workspace(deep)
        assert loc.root == tmp_path.resolve()

    def test_both_markers_at_same_level_is_ambiguous(self, tmp_path: Path) -> None:
        (tmp_path / WORKSPACE_MARKER).write_text("name='t'\n")
        (tmp_path / SET_MARKER).write_text("name='s'\n")
        with pytest.raises(WorkspaceNotFoundError, match="both"):
            discover_workspace(tmp_path)

    def test_no_marker_raises(self, tmp_path: Path) -> None:
        with pytest.raises(WorkspaceNotFoundError, match=r"no brunch\.toml"):
            discover_workspace(tmp_path)

    def test_inner_workspace_wins_over_outer_set(self, tmp_path: Path) -> None:
        (tmp_path / SET_MARKER).write_text("name='s'\n")
        inner = tmp_path / "inner"
        inner.mkdir()
        (inner / WORKSPACE_MARKER).write_text("name='w'\n")
        loc = discover_workspace(inner)
        assert loc.mode == "workspace"
        assert loc.root == inner.resolve()


class TestDiscoverSetMembers:
    def _make_member(self, parent: Path, name: str) -> Path:
        d = parent / name
        d.mkdir()
        (d / WORKSPACE_MARKER).write_text(f'name = "{name}"\n', encoding="utf-8")
        return d

    def test_empty_set_returns_no_members(self, tmp_path: Path) -> None:
        assert discover_set_members(tmp_path) == []

    def test_returns_direct_children_with_brunch_toml(self, tmp_path: Path) -> None:
        a = self._make_member(tmp_path, "task-a")
        b = self._make_member(tmp_path, "task-b")
        members = discover_set_members(tmp_path)
        assert {m.root for m in members} == {a, b}
        # All members are workspace mode.
        assert all(m.mode == "workspace" for m in members)

    def test_ignores_non_workspace_dirs(self, tmp_path: Path) -> None:
        self._make_member(tmp_path, "task-a")
        (tmp_path / "scratch").mkdir()
        (tmp_path / "scratch" / "notes.md").write_text("x\n", encoding="utf-8")
        members = discover_set_members(tmp_path)
        assert {m.root.name for m in members} == {"task-a"}

    def test_ignores_files_at_set_root(self, tmp_path: Path) -> None:
        self._make_member(tmp_path, "task-a")
        (tmp_path / "brunch-set.toml").write_text('name = "s"\n', encoding="utf-8")
        (tmp_path / "notes.md").write_text("x\n", encoding="utf-8")
        members = discover_set_members(tmp_path)
        assert {m.root.name for m in members} == {"task-a"}

    def test_results_are_sorted_by_name(self, tmp_path: Path) -> None:
        self._make_member(tmp_path, "task-c")
        self._make_member(tmp_path, "task-a")
        self._make_member(tmp_path, "task-b")
        members = discover_set_members(tmp_path)
        assert [m.root.name for m in members] == ["task-a", "task-b", "task-c"]

    def test_does_not_follow_symlinks(self, tmp_path: Path) -> None:
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / WORKSPACE_MARKER).write_text('name = "x"\n', encoding="utf-8")
        set_root = tmp_path / "set"
        set_root.mkdir()
        (set_root / "link").symlink_to(outside)
        members = discover_set_members(set_root)
        assert members == []

    def test_nonexistent_set_root_returns_empty(self, tmp_path: Path) -> None:
        assert discover_set_members(tmp_path / "nope") == []
