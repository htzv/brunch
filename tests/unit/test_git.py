from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from brunch.errors import GitError
from brunch.git import (
    _parse_porcelain_v2,
    _parse_worktree_list,
    add_worktree,
    branch_exists,
    current_branch,
    get_status,
    is_git_repo,
    remove_worktree,
    worktree_list,
)


class TestIsGitRepo:
    def test_true_for_git_repo(self, make_canonical: Callable[..., Path]) -> None:
        assert is_git_repo(make_canonical()) is True

    def test_false_for_non_repo(self, tmp_path: Path) -> None:
        assert is_git_repo(tmp_path) is False

    def test_false_for_missing_path(self, tmp_path: Path) -> None:
        assert is_git_repo(tmp_path / "does-not-exist") is False


class TestCurrentBranch:
    def test_returns_initial_branch(self, make_canonical: Callable[..., Path]) -> None:
        repo = make_canonical(initial_branch="main")
        assert current_branch(repo) == "main"

    def test_returns_none_when_detached(self, make_canonical: Callable[..., Path]) -> None:
        repo = make_canonical()
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        subprocess.run(
            ["git", "checkout", "--detach", sha],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert current_branch(repo) is None

    def test_raises_on_non_repo(self, tmp_path: Path) -> None:
        with pytest.raises(GitError):
            current_branch(tmp_path)


class TestGetStatus:
    def test_clean_repo(self, make_canonical: Callable[..., Path]) -> None:
        s = get_status(make_canonical())
        assert s.branch == "main"
        assert s.ahead == 0 and s.behind == 0
        assert s.has_uncommitted is False
        assert s.has_untracked is False

    def test_detects_uncommitted(self, make_canonical: Callable[..., Path]) -> None:
        repo = make_canonical()
        (repo / "README.md").write_text("changed\n", encoding="utf-8")
        s = get_status(repo)
        assert s.has_uncommitted is True

    def test_detects_untracked(self, make_canonical: Callable[..., Path]) -> None:
        repo = make_canonical()
        (repo / "new-file.txt").write_text("hello\n", encoding="utf-8")
        s = get_status(repo)
        assert s.has_untracked is True


class TestWorktreeList:
    def test_lists_main_only_initially(self, make_canonical: Callable[..., Path]) -> None:
        repo = make_canonical()
        wts = worktree_list(repo)
        assert len(wts) == 1
        assert wts[0].branch == "main"
        assert wts[0].detached is False

    def test_lists_added_worktree(
        self,
        make_canonical: Callable[..., Path],
        tmp_path: Path,
        worktree_factory: Callable[..., None],
    ) -> None:
        repo = make_canonical()
        target = tmp_path / "extra-worktree"
        worktree_factory(repo, target, branch="feature-x", base="main")
        wts = worktree_list(repo)
        branches = {w.branch for w in wts}
        assert branches == {"main", "feature-x"}


class TestPorcelainV2Parser:
    def test_minimal_clean(self) -> None:
        text = "# branch.oid abc\n# branch.head main\n"
        s = _parse_porcelain_v2(text)
        assert s.branch == "main"
        assert not s.has_uncommitted

    def test_detached(self) -> None:
        text = "# branch.head (detached)\n"
        s = _parse_porcelain_v2(text)
        assert s.branch is None

    def test_ahead_behind(self) -> None:
        text = "# branch.head main\n# branch.ab +3 -2\n"
        s = _parse_porcelain_v2(text)
        assert s.ahead == 3 and s.behind == 2

    def test_uncommitted_and_untracked(self) -> None:
        text = (
            "# branch.head main\n1 .M N... 100644 100644 100644 abc abc README.md\n? new-file.txt\n"
        )
        s = _parse_porcelain_v2(text)
        assert s.has_uncommitted is True
        assert s.has_untracked is True


class TestWorktreeListParser:
    def test_single_worktree(self) -> None:
        text = "worktree /a/b\nHEAD abc123\nbranch refs/heads/main\n\n"
        out = _parse_worktree_list(text)
        assert len(out) == 1
        assert out[0].path == Path("/a/b")
        assert out[0].head == "abc123"
        assert out[0].branch == "main"
        assert out[0].detached is False

    def test_multiple_with_detached(self) -> None:
        text = (
            "worktree /a/b\nHEAD abc\nbranch refs/heads/main\n\n"
            "worktree /a/c\nHEAD def\ndetached\n\n"
        )
        out = _parse_worktree_list(text)
        assert len(out) == 2
        assert out[1].detached is True
        assert out[1].branch is None

    def test_empty_input(self) -> None:
        assert _parse_worktree_list("") == []

    def test_handles_missing_trailing_blank(self) -> None:
        # `git worktree list --porcelain` always ends with a blank line, but
        # we should still flush a record if it does not.
        text = "worktree /a/b\nHEAD abc\nbranch refs/heads/main"
        out = _parse_worktree_list(text)
        assert len(out) == 1
        assert out[0].path == Path("/a/b")


class TestBranchExists:
    def test_main_exists_after_init(self, make_canonical: Callable[..., Path]) -> None:
        repo = make_canonical()
        assert branch_exists(repo, "main") is True

    def test_unknown_branch_does_not_exist(self, make_canonical: Callable[..., Path]) -> None:
        repo = make_canonical()
        assert branch_exists(repo, "nope") is False


class TestAddWorktree:
    def test_creates_new_branch(self, make_canonical: Callable[..., Path], tmp_path: Path) -> None:
        repo = make_canonical()
        target = tmp_path / "new-worktree"
        add_worktree(repo, target, branch="feature-x", base="main")
        assert target.is_dir()
        assert (target / ".git").exists()
        # New worktree is on its branch.
        assert current_branch(target) == "feature-x"
        # Branch shows up in `git worktree list`.
        branches = {w.branch for w in worktree_list(repo)}
        assert "feature-x" in branches

    def test_reuses_existing_branch(
        self, make_canonical: Callable[..., Path], tmp_path: Path
    ) -> None:
        repo = make_canonical()
        # Create the branch in the canonical first (without a worktree).
        import subprocess

        subprocess.run(
            ["git", "branch", "preexisting", "main"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        target = tmp_path / "wt"
        add_worktree(repo, target, branch="preexisting", base="main")
        assert current_branch(target) == "preexisting"

    def test_makes_parent_dirs(self, make_canonical: Callable[..., Path], tmp_path: Path) -> None:
        repo = make_canonical()
        target = tmp_path / "a" / "b" / "c" / "wt"
        add_worktree(repo, target, branch="feat", base="main")
        assert target.is_dir()


class TestRemoveWorktree:
    def test_removes_clean_worktree(
        self, make_canonical: Callable[..., Path], tmp_path: Path
    ) -> None:
        repo = make_canonical()
        target = tmp_path / "wt"
        add_worktree(repo, target, branch="feat", base="main")
        remove_worktree(repo, target)
        assert not target.exists()
        branches = {w.branch for w in worktree_list(repo)}
        assert "feat" not in branches  # the worktree, that is — branch still exists

    def test_force_removes_dirty_worktree(
        self, make_canonical: Callable[..., Path], tmp_path: Path
    ) -> None:
        repo = make_canonical()
        target = tmp_path / "wt"
        add_worktree(repo, target, branch="feat", base="main")
        (target / "dirty.txt").write_text("changes\n", encoding="utf-8")
        # Without force, git would refuse.
        remove_worktree(repo, target, force=True)
        assert not target.exists()
