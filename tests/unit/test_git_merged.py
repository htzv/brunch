"""Merged-work signals, against real repos with a real origin and real squash merges."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from brunch import git_merged
from brunch.errors import GitError
from brunch.git import get_status
from tests.conftest import OriginRepo, _git

MakeOrigin = Callable[..., OriginRepo]


def _edit_and_commit(repo: Path, filename: str, message: str) -> None:
    (repo / filename).write_text(f"{message}\n", encoding="utf-8")
    _git(["add", filename], cwd=repo)
    _git(["commit", "-m", message], cwd=repo)


def _feature_branch(origin: OriginRepo, *, commits: int) -> Path:
    """A pushed branch ``feat`` with ``commits`` commits, checked out in the canonical."""

    _git(["checkout", "-b", "feat"], cwd=origin.canonical)
    for n in range(commits):
        _edit_and_commit(origin.canonical, f"feat-{n}.txt", f"feat {n}")
    _git(["push", "-u", "origin", "feat"], cwd=origin.canonical)
    return origin.canonical


class TestIsAncestor:
    def test_branch_merged_by_fast_forward(self, make_origin: MakeOrigin) -> None:
        origin = make_origin()
        repo = _feature_branch(origin, commits=1)
        _git(["push", "origin", "feat:main"], cwd=repo)
        _git(["fetch", "origin"], cwd=repo)
        assert git_merged.is_ancestor(repo, "HEAD", "origin/main")

    def test_branch_with_commits_main_lacks(self, make_origin: MakeOrigin) -> None:
        origin = make_origin()
        repo = _feature_branch(origin, commits=1)
        assert not git_merged.is_ancestor(repo, "HEAD", "origin/main")

    def test_unknown_ref_is_an_error_not_a_no(self, make_origin: MakeOrigin) -> None:
        origin = make_origin()
        with pytest.raises(GitError):
            git_merged.is_ancestor(origin.canonical, "no-such-ref", "HEAD")


class TestCherryUnmerged:
    def test_single_commit_squash_is_recognised(self, make_origin: MakeOrigin) -> None:
        origin = make_origin()
        repo = _feature_branch(origin, commits=1)
        origin.squash_merge("feat")
        _git(["fetch", "origin"], cwd=repo)
        assert git_merged.cherry_unmerged(repo, "origin/main") == 0

    def test_multi_commit_squash_is_not_recognised(self, make_origin: MakeOrigin) -> None:
        """A squash of several commits matches none of them: only the tree check sees it."""

        origin = make_origin()
        repo = _feature_branch(origin, commits=2)
        origin.squash_merge("feat")
        _git(["fetch", "origin"], cwd=repo)
        assert git_merged.cherry_unmerged(repo, "origin/main") == 2

    def test_rebased_commits_are_recognised(self, make_origin: MakeOrigin) -> None:
        origin = make_origin()
        repo = _feature_branch(origin, commits=2)
        origin.advance()
        _git(["fetch", "origin"], cwd=repo)
        _git(["rebase", "origin/main"], cwd=repo)
        _git(["push", "--force", "origin", "feat:main"], cwd=repo)
        _git(["fetch", "origin"], cwd=repo)
        _git(["reset", "--hard", "ORIG_HEAD"], cwd=repo)
        assert git_merged.cherry_unmerged(repo, "origin/main") == 0

    def test_counts_commits_that_never_reached_upstream(self, make_origin: MakeOrigin) -> None:
        origin = make_origin()
        repo = _feature_branch(origin, commits=3)
        assert git_merged.cherry_unmerged(repo, "origin/main") == 3


class TestUpstreamGone:
    def test_present_upstream(self, make_origin: MakeOrigin) -> None:
        origin = make_origin()
        repo = _feature_branch(origin, commits=1)
        assert not git_merged.upstream_gone(repo, "feat")

    def test_deleted_upstream_is_invisible_until_a_pruning_fetch(
        self, make_origin: MakeOrigin
    ) -> None:
        origin = make_origin()
        repo = _feature_branch(origin, commits=1)
        origin.squash_merge("feat")

        _git(["fetch", "origin"], cwd=repo)
        assert not git_merged.upstream_gone(repo, "feat")

        _git(["fetch", "--prune", "origin"], cwd=repo)
        assert git_merged.upstream_gone(repo, "feat")

    def test_gone_upstream_hides_unpushed_commits_from_status(
        self, make_origin: MakeOrigin
    ) -> None:
        """Why a gone upstream needs its own check: `ahead` reads 0 with a commit unpushed."""

        origin = make_origin()
        repo = _feature_branch(origin, commits=1)
        origin.squash_merge("feat")
        _edit_and_commit(repo, "late.txt", "late work, never pushed")
        _git(["fetch", "--prune", "origin"], cwd=repo)

        status = get_status(repo)

        assert git_merged.upstream_gone(repo, "feat")
        assert status.upstream == "origin/feat"
        assert status.ahead == 0

    def test_branch_without_upstream_is_not_gone(self, make_origin: MakeOrigin) -> None:
        origin = make_origin()
        _git(["branch", "local-only"], cwd=origin.canonical)
        assert not git_merged.upstream_gone(origin.canonical, "local-only")

    def test_unknown_branch_is_not_gone(self, make_origin: MakeOrigin) -> None:
        assert not git_merged.upstream_gone(make_origin().canonical, "nope")


class TestTreeContainedIn:
    def _squashed(self, origin: OriginRepo, commits: int) -> Path:
        repo = _feature_branch(origin, commits=commits)
        origin.squash_merge("feat")
        _git(["fetch", "--prune", "origin"], cwd=repo)
        return repo

    def test_multi_commit_squash_is_contained(self, make_origin: MakeOrigin) -> None:
        origin = make_origin()
        repo = self._squashed(origin, commits=3)
        assert git_merged.tree_contained_in(repo, "origin/main")

    def test_still_contained_after_main_moves_on(self, make_origin: MakeOrigin) -> None:
        origin = make_origin()
        repo = self._squashed(origin, commits=2)
        origin.advance()
        _git(["fetch", "origin"], cwd=repo)
        assert git_merged.tree_contained_in(repo, "origin/main")

    def test_work_added_after_the_squash_is_not_contained(self, make_origin: MakeOrigin) -> None:
        origin = make_origin()
        repo = self._squashed(origin, commits=2)
        _edit_and_commit(repo, "late.txt", "late work")
        assert not git_merged.tree_contained_in(repo, "origin/main")

    def test_unmerged_branch_is_not_contained(self, make_origin: MakeOrigin) -> None:
        origin = make_origin()
        repo = _feature_branch(origin, commits=1)
        assert not git_merged.tree_contained_in(repo, "origin/main")

    def test_conflict_with_later_edits_cannot_be_proven(self, make_origin: MakeOrigin) -> None:
        origin = make_origin()
        repo = _feature_branch(origin, commits=0)
        (repo / "README.md").write_text("branch edit\n", encoding="utf-8")
        _git(["commit", "-am", "branch edit"], cwd=repo)
        _git(["push", "-u", "origin", "feat"], cwd=repo)
        origin.squash_merge("feat")
        origin.edit_main("README.md", "later edit of the same lines\n")
        _git(["fetch", "--prune", "origin"], cwd=repo)
        assert not git_merged.tree_contained_in(repo, "origin/main")

    def test_unknown_ref_is_not_contained(self, make_origin: MakeOrigin) -> None:
        assert not git_merged.tree_contained_in(make_origin().canonical, "no-such-ref")

    def test_commits_without_content_are_not_part_of_the_proof(
        self, make_origin: MakeOrigin
    ) -> None:
        """Contract: this proves content is in `ref`, not that commits are reachable.

        An empty commit never reached main, and its message is not there, yet
        nothing of value is lost: a squash merge drops it as well, and removing a
        worktree keeps the branch.
        """

        origin = make_origin()
        repo = origin.canonical
        _git(["checkout", "-b", "feat"], cwd=repo)
        _git(["commit", "--allow-empty", "-m", "an intent with no content"], cwd=repo)

        assert not git_merged.is_ancestor(repo, "HEAD", "origin/main")
        assert git_merged.tree_contained_in(repo, "origin/main")

    def test_a_change_and_its_revert_are_not_part_of_the_proof(
        self, make_origin: MakeOrigin
    ) -> None:
        origin = make_origin()
        repo = origin.canonical
        _git(["checkout", "-b", "feat"], cwd=repo)
        _edit_and_commit(repo, "scratch.txt", "try something")
        _git(["revert", "--no-edit", "HEAD"], cwd=repo)

        assert not git_merged.is_ancestor(repo, "HEAD", "origin/main")
        assert git_merged.tree_contained_in(repo, "origin/main")
