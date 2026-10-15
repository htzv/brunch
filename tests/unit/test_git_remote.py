"""Remote choice, fetching and start points, against real repos with a real origin."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from brunch import git_remote
from brunch.errors import FetchError, RemoteError
from tests.conftest import OriginRepo, _git

MakeOrigin = Callable[..., OriginRepo]


def _rev(repo: Path, ref: str) -> str:
    return _git(["rev-parse", ref], cwd=repo).strip()


class TestRemotes:
    def test_lists_configured_remotes(self, make_origin: MakeOrigin) -> None:
        origin = make_origin()
        _git(["remote", "add", "upstream", str(origin.bare)], cwd=origin.canonical)
        assert sorted(git_remote.remotes(origin.canonical)) == ["origin", "upstream"]

    def test_repo_without_remotes_has_none(self, make_canonical: Callable[..., Path]) -> None:
        assert git_remote.remotes(make_canonical()) == []


class TestFetchRemote:
    def test_brings_in_new_commits(self, make_origin: MakeOrigin) -> None:
        origin = make_origin()
        tip = origin.advance()
        git_remote.fetch_remote(origin.canonical, "origin")
        assert _rev(origin.canonical, "origin/main") == tip

    def test_unreachable_remote_raises_fetch_error_with_offline_hint(
        self, make_origin: MakeOrigin, tmp_path: Path
    ) -> None:
        origin = make_origin()
        _git(["remote", "set-url", "origin", str(tmp_path / "gone.git")], cwd=origin.canonical)
        with pytest.raises(FetchError) as caught:
            git_remote.fetch_remote(origin.canonical, "origin")
        assert "origin" in str(caught.value)
        assert caught.value.hint is not None and "--no-fetch" in caught.value.hint


class TestResolveRemote:
    def test_requested_name_wins(self, make_origin: MakeOrigin) -> None:
        origin = make_origin()
        _git(["remote", "add", "upstream", str(origin.bare)], cwd=origin.canonical)
        assert git_remote.resolve_remote(origin.canonical, "upstream") == "upstream"

    def test_unknown_requested_name_lists_the_remotes(self, make_origin: MakeOrigin) -> None:
        origin = make_origin()
        with pytest.raises(RemoteError, match=r"no remote named 'nope'.*origin"):
            git_remote.resolve_remote(origin.canonical, "nope")

    def test_configured_default_beats_origin(self, make_origin: MakeOrigin) -> None:
        origin = make_origin()
        _git(["remote", "add", "upstream", str(origin.bare)], cwd=origin.canonical)
        _git(["config", "checkout.defaultRemote", "upstream"], cwd=origin.canonical)
        assert git_remote.resolve_remote(origin.canonical, None) == "upstream"

    def test_the_only_remote_is_used_whatever_it_is_called(self, make_origin: MakeOrigin) -> None:
        origin = make_origin()
        _git(["remote", "rename", "origin", "company"], cwd=origin.canonical)
        assert git_remote.resolve_remote(origin.canonical, None) == "company"

    def test_origin_is_chosen_among_several(self, make_origin: MakeOrigin) -> None:
        origin = make_origin()
        _git(["remote", "add", "upstream", str(origin.bare)], cwd=origin.canonical)
        assert git_remote.resolve_remote(origin.canonical, None) == "origin"

    def test_several_remotes_without_origin_or_default_is_an_error(
        self, make_origin: MakeOrigin
    ) -> None:
        origin = make_origin()
        _git(["remote", "rename", "origin", "a"], cwd=origin.canonical)
        _git(["remote", "add", "b", str(origin.bare)], cwd=origin.canonical)
        with pytest.raises(RemoteError) as caught:
            git_remote.resolve_remote(origin.canonical, None)
        assert "a, b" in str(caught.value)
        assert caught.value.hint is not None and "--remote" in caught.value.hint

    def test_no_remotes_resolves_to_none(self, make_canonical: Callable[..., Path]) -> None:
        assert git_remote.resolve_remote(make_canonical(), None) is None

    def test_asking_for_a_remote_in_a_repo_without_any_is_an_error(
        self, make_canonical: Callable[..., Path]
    ) -> None:
        with pytest.raises(RemoteError, match="remotes: none"):
            git_remote.resolve_remote(make_canonical(), "origin")


class TestDefaultBranch:
    def test_reads_the_remote_head(self, make_origin: MakeOrigin) -> None:
        origin = make_origin()
        assert git_remote.default_branch(origin.canonical, "origin") == "main"

    def test_follows_a_remote_whose_default_is_not_main(self, make_origin: MakeOrigin) -> None:
        origin = make_origin()
        origin.publish_branch("develop")
        _git(["fetch", "origin"], cwd=origin.canonical)
        _git(["remote", "set-head", "origin", "develop"], cwd=origin.canonical)
        assert git_remote.default_branch(origin.canonical, "origin") == "develop"

    def test_falls_back_to_main_without_a_remote_head(
        self, make_canonical: Callable[..., Path]
    ) -> None:
        assert git_remote.default_branch(make_canonical(), "origin") == "main"


class TestResolveStartPoint:
    def test_default_branch_starts_from_the_fetched_remote_tip(
        self, make_origin: MakeOrigin
    ) -> None:
        origin = make_origin()
        origin.advance()
        git_remote.fetch_remote(origin.canonical, "origin")
        assert git_remote.resolve_start_point(origin.canonical, "origin", "main") == "origin/main"

    def test_other_base_starts_from_the_local_branch(self, make_origin: MakeOrigin) -> None:
        """A stack parent may have unpushed commits, so its stale origin copy loses."""

        origin = make_origin()
        origin.publish_branch("parent")
        _git(["fetch", "origin"], cwd=origin.canonical)
        _git(["branch", "parent", "origin/parent"], cwd=origin.canonical)
        assert git_remote.resolve_start_point(origin.canonical, "origin", "parent") == "parent"

    def test_base_that_exists_only_on_the_remote_uses_the_remote_copy(
        self, make_origin: MakeOrigin
    ) -> None:
        origin = make_origin()
        origin.publish_branch("parent")
        _git(["fetch", "origin"], cwd=origin.canonical)
        assert (
            git_remote.resolve_start_point(origin.canonical, "origin", "parent") == "origin/parent"
        )

    def test_a_full_ref_is_used_as_given(self, make_origin: MakeOrigin) -> None:
        origin = make_origin()
        assert (
            git_remote.resolve_start_point(origin.canonical, "origin", "origin/main")
            == "origin/main"
        )

    def test_without_a_remote_the_base_is_used_as_given(
        self, make_canonical: Callable[..., Path]
    ) -> None:
        assert git_remote.resolve_start_point(make_canonical(), None, "main") == "main"

    def test_default_branch_not_yet_fetched_falls_back_to_the_local_branch(
        self, make_canonical: Callable[..., Path]
    ) -> None:
        repo = make_canonical()
        _git(["remote", "add", "origin", str(repo)], cwd=repo)
        assert git_remote.resolve_start_point(repo, "origin", "main") == "main"


class TestCountUnpublishedCommits:
    def _branch_from_stale_main(self, origin: OriginRepo, tmp_path: Path) -> Path:
        origin.advance()
        git_remote.fetch_remote(origin.canonical, "origin")
        target = tmp_path / "wt"
        _git(
            ["worktree", "add", "--no-track", "-b", "feat", str(target), "origin/main"],
            cwd=origin.canonical,
        )
        return target

    def test_commits_the_fetch_brought_in_are_not_counted(
        self, make_origin: MakeOrigin, tmp_path: Path
    ) -> None:
        origin = make_origin()
        wt = self._branch_from_stale_main(origin, tmp_path)
        assert git_remote.count_unpublished_commits(wt, "main") == 0

    def test_own_commits_are_counted(self, make_origin: MakeOrigin, tmp_path: Path) -> None:
        origin = make_origin()
        wt = self._branch_from_stale_main(origin, tmp_path)
        _git(["commit", "--allow-empty", "-m", "mine"], cwd=wt)
        assert git_remote.count_unpublished_commits(wt, "main") == 1

    def test_commits_only_in_the_local_base_are_not_counted(
        self, make_origin: MakeOrigin, tmp_path: Path
    ) -> None:
        origin = make_origin()
        _git(["commit", "--allow-empty", "-m", "local main only"], cwd=origin.canonical)
        wt = tmp_path / "wt"
        _git(["worktree", "add", "-b", "feat", str(wt), "main"], cwd=origin.canonical)
        assert git_remote.count_unpublished_commits(wt, "main") == 0

    def test_ambiguous_remotes_fall_back_to_the_local_base(
        self, make_origin: MakeOrigin, tmp_path: Path
    ) -> None:
        origin = make_origin()
        _git(["remote", "rename", "origin", "a"], cwd=origin.canonical)
        _git(["remote", "add", "b", str(origin.bare)], cwd=origin.canonical)
        wt = tmp_path / "wt"
        _git(["worktree", "add", "-b", "feat", str(wt), "main"], cwd=origin.canonical)
        _git(["commit", "--allow-empty", "-m", "mine"], cwd=wt)
        assert git_remote.count_unpublished_commits(wt, "main") == 1

    def test_repo_without_remotes_compares_against_the_local_base(
        self, make_canonical: Callable[..., Path], tmp_path: Path
    ) -> None:
        repo = make_canonical()
        wt = tmp_path / "wt"
        _git(["worktree", "add", "-b", "feat", str(wt), "main"], cwd=repo)
        _git(["commit", "--allow-empty", "-m", "mine"], cwd=wt)
        assert git_remote.count_unpublished_commits(wt, "main") == 1
