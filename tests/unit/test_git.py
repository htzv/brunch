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
    count_commits_ahead_of,
    current_branch,
    fetch,
    get_status,
    has_remote,
    is_git_repo,
    pull,
    rebase,
    rebase_in_progress,
    remove_worktree,
    rev_parse_verify,
    worktree_list,
    worktree_prune,
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


class TestCountCommitsAheadOf:
    def test_zero_when_no_extra_commits(
        self,
        make_canonical: Callable[..., Path],
        tmp_path: Path,
        worktree_factory: Callable[..., None],
    ) -> None:
        repo = make_canonical()
        wt = tmp_path / "wt"
        worktree_factory(repo, wt, branch="feat", base="main")
        assert count_commits_ahead_of(wt, "main") == 0

    def test_counts_local_commits(
        self,
        make_canonical: Callable[..., Path],
        tmp_path: Path,
        worktree_factory: Callable[..., None],
    ) -> None:
        repo = make_canonical()
        wt = tmp_path / "wt"
        worktree_factory(repo, wt, branch="feat", base="main")
        import subprocess

        for i in range(3):
            (wt / f"f{i}.txt").write_text(f"{i}\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=wt, check=True, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", f"c{i}"],
                cwd=wt,
                check=True,
                capture_output=True,
            )
        assert count_commits_ahead_of(wt, "main") == 3

    def test_unknown_base_returns_zero(
        self,
        make_canonical: Callable[..., Path],
        tmp_path: Path,
        worktree_factory: Callable[..., None],
    ) -> None:
        repo = make_canonical()
        wt = tmp_path / "wt"
        worktree_factory(repo, wt, branch="feat", base="main")
        assert count_commits_ahead_of(wt, "no-such-branch") == 0


class TestWorktreePrune:
    def test_prunes_dangling_refs(
        self,
        make_canonical: Callable[..., Path],
        tmp_path: Path,
        worktree_factory: Callable[..., None],
    ) -> None:
        import shutil

        repo = make_canonical()
        wt = tmp_path / "wt"
        worktree_factory(repo, wt, branch="orphan", base="main")
        shutil.rmtree(wt)
        # Before prune, the canonical still has a ref pointing at the gone path.
        before = {w.path for w in worktree_list(repo)}
        assert wt in before
        worktree_prune(repo)
        after = {w.path for w in worktree_list(repo)}
        assert wt not in after


class TestRevParseVerify:
    def test_existing_branch(self, make_canonical: Callable[..., Path]) -> None:
        repo = make_canonical()
        assert rev_parse_verify(repo, "main") is True

    def test_missing_branch(self, make_canonical: Callable[..., Path]) -> None:
        repo = make_canonical()
        assert rev_parse_verify(repo, "no-such-branch") is False

    def test_missing_remote_tracking(self, make_canonical: Callable[..., Path]) -> None:
        repo = make_canonical()
        assert rev_parse_verify(repo, "origin/main") is False


class TestHasRemote:
    def test_repo_with_no_remote(self, make_canonical: Callable[..., Path]) -> None:
        assert has_remote(make_canonical()) is False

    def test_repo_with_origin(self, make_canonical: Callable[..., Path]) -> None:
        a = make_canonical("origin-target")
        b = make_canonical("with-origin")
        import subprocess

        subprocess.run(
            ["git", "remote", "add", "origin", str(a)],
            cwd=b,
            check=True,
            capture_output=True,
        )
        assert has_remote(b) is True


class TestFetch:
    def test_fetch_from_origin_succeeds(self, make_canonical: Callable[..., Path]) -> None:
        upstream = make_canonical("upstream")
        downstream = make_canonical("downstream")
        import subprocess

        subprocess.run(
            ["git", "remote", "add", "origin", str(upstream)],
            cwd=downstream,
            check=True,
            capture_output=True,
        )
        fetch(downstream)
        # origin/main should now resolve.
        assert rev_parse_verify(downstream, "origin/main") is True

    def test_fetch_without_remote_is_noop(self, make_canonical: Callable[..., Path]) -> None:
        # Modern git returns 0 with no output when no remote is configured;
        # callers don't need to special-case the "no remote" path.
        fetch(make_canonical())


class TestPull:
    def test_pull_brings_in_new_commits(
        self, make_canonical: Callable[..., Path], tmp_path: Path
    ) -> None:
        upstream = make_canonical("upstream")
        # Clone via filesystem so origin is wired up.
        import subprocess

        downstream = tmp_path / "downstream"
        subprocess.run(
            ["git", "clone", str(upstream), str(downstream)],
            check=True,
            capture_output=True,
        )
        # Add a commit upstream.
        (upstream / "new.txt").write_text("hi\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=upstream, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "upstream-commit"],
            cwd=upstream,
            check=True,
            capture_output=True,
        )
        pull(downstream)
        assert (downstream / "new.txt").exists()


class TestRebase:
    def test_rebase_linear_succeeds(
        self,
        make_canonical: Callable[..., Path],
        tmp_path: Path,
        worktree_factory: Callable[..., None],
    ) -> None:
        repo = make_canonical()
        wt = tmp_path / "wt"
        worktree_factory(repo, wt, branch="feature", base="main")
        # Advance main by one commit (in the canonical's main worktree).
        import subprocess

        (repo / "moved.txt").write_text("x\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "advance-main"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        # Now rebase the feature worktree onto the new main.
        rebase(wt, "main")
        # The worktree should now also have moved.txt.
        assert (wt / "moved.txt").exists()

    def test_rebase_in_progress_after_conflict(
        self,
        make_canonical: Callable[..., Path],
        tmp_path: Path,
        worktree_factory: Callable[..., None],
    ) -> None:
        from brunch.errors import GitError

        repo = make_canonical()
        wt = tmp_path / "wt"
        worktree_factory(repo, wt, branch="feature", base="main")
        # Conflicting edit on feature.
        (wt / "README.md").write_text("feature change\n", encoding="utf-8")
        import subprocess

        subprocess.run(["git", "add", "."], cwd=wt, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "feature-edit"],
            cwd=wt,
            check=True,
            capture_output=True,
        )
        # Conflicting edit on main (in the canonical).
        (repo / "README.md").write_text("main change\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "main-edit"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        # Rebase should hit a conflict.
        with pytest.raises(GitError):
            rebase(wt, "main")
        assert rebase_in_progress(wt) is True
