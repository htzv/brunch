"""Has this branch's work already reached another ref?

Four independent signals, each safe to be wrong in one direction only: a
``False`` means "not proven merged", never "proven unmerged". A squash merge
leaves no commit in common, so only the tree comparison can see it.
"""

from __future__ import annotations

from pathlib import Path

from brunch.errors import GitError
from brunch.git import rev_parse_verify, run_git

GIT_EXIT_NO = 1
CHERRY_UNMERGED_MARK = "+"
GONE_TRACK = "[gone]"


def is_ancestor(path: Path, ancestor: str, descendant: str = "HEAD") -> bool:
    """True if every commit of ``ancestor`` is reachable from ``descendant``.

    Catches fast-forward and merge-commit merges.
    """

    result = run_git(["merge-base", "--is-ancestor", ancestor, descendant], cwd=path, check=False)
    if result.returncode == 0:
        return True
    if result.returncode == GIT_EXIT_NO:
        return False
    raise GitError(f"cannot compare {ancestor!r} with {descendant!r}: {result.stderr.strip()}")


def cherry_unmerged(path: Path, upstream: str, head: str = "HEAD") -> int:
    """Commits of ``head`` with no patch-equivalent commit in ``upstream``.

    0 means every commit was applied there, which catches rebase merges and a
    squash of a single commit. A squash of several commits shows them all as
    unmerged.
    """

    result = run_git(["cherry", upstream, head], cwd=path)
    return sum(1 for line in result.stdout.splitlines() if line.startswith(CHERRY_UNMERGED_MARK))


def upstream_gone(path: Path, branch: str) -> bool:
    """True if ``branch`` tracks a remote branch that no longer exists.

    Only visible after a fetch with pruning: until then the remote-tracking ref
    is still there. A gone upstream also hides ``ahead``: git leaves
    ``branch.ab`` out of ``status``, so unpushed commits read as zero.
    """

    result = run_git(
        ["for-each-ref", "--format=%(upstream:track)", f"refs/heads/{branch}"],
        cwd=path,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == GONE_TRACK


def tree_contained_in(path: Path, ref: str, head: str = "HEAD") -> bool:
    """True if merging ``head`` into ``ref`` would change nothing.

    That is how a squash-merged branch looks once its changes are in ``ref``,
    even after ``ref`` has moved on. Work added to the branch after the squash
    changes the result, and a conflict (``ref`` edited the same lines later)
    cannot be proven, so both give False. Needs git 2.38 or newer; older git
    gives False.

    This proves that the *content* is in ``ref``, not that the commits are
    reachable from it. Commits that change no content (an empty commit, a change
    and its revert) and commit messages are not covered; a squash merge discards
    them too, and removing a worktree never deletes its branch.
    """

    if not (rev_parse_verify(path, ref) and rev_parse_verify(path, head)):
        return False
    merged = run_git(["merge-tree", "--write-tree", ref, head], cwd=path, check=False)
    if merged.returncode != 0:
        return False
    ref_tree = run_git(["rev-parse", f"{ref}^{{tree}}"], cwd=path).stdout.strip()
    return merged.stdout.splitlines()[0].strip() == ref_tree
