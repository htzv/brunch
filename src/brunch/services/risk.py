"""Is it safe to remove a repo's worktree? The one answer `br rm` and `br drop` share.

A worktree is at risk when removing it could lose work: uncommitted changes,
untracked files, or commits that exist nowhere else. "Nowhere else" is git's own
answer: commits that no remote-tracking branch contains (and that the local base
branch does not contain), unless the remote copy of the base already has their
content (a rebase or squash merge). Run :func:`refresh_remotes` first so those
branches are current.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from brunch import git, git_merged, git_remote
from brunch.errors import GitError, RepoSpecError
from brunch.models import MergedSignal, RepoEntry, RmRisk, ToolConfig
from brunch.paths import canonical_clone_path, parse_repo_spec


def clones_to_refresh(
    entries: Iterable[RepoEntry], workspace_root: Path, config: ToolConfig
) -> list[Path]:
    """The clones behind ``entries`` whose worktree exists, which are the ones that matter."""

    clones: list[Path] = []
    for entry in entries:
        try:
            spec = parse_repo_spec(entry.repo, default_forge=config.default_forge)
        except RepoSpecError:
            continue
        canonical = canonical_clone_path(spec, root=config.root)
        if (workspace_root / spec.name).exists() and git.is_git_repo(canonical):
            clones.append(canonical)
    return clones


def refresh_remotes(clones: Iterable[Path]) -> list[str]:
    """Fetch and prune every remote, by name, of each distinct clone, once.

    Like git, work offline: a failed fetch is not an error. It comes back as a
    warning, and the verdict then rests on the remote refs from the last fetch.
    """

    return [
        f"{clone}: {failure}"
        for clone in dict.fromkeys(clones)
        for failure in git_remote.fetch_every_remote(clone)
    ]


def assess_repo(entry: RepoEntry, workspace_root: Path, config: ToolConfig) -> RmRisk:
    """What would be lost by removing ``entry``'s worktree under ``workspace_root``."""

    try:
        spec = parse_repo_spec(entry.repo, default_forge=config.default_forge)
    except RepoSpecError:
        return RmRisk(repo=entry.repo, short_name=entry.repo)

    worktree = workspace_root / spec.name
    if not worktree.exists() or not git.is_git_repo(worktree):
        return RmRisk(repo=entry.repo, short_name=spec.name)

    try:
        status = git.get_status(worktree)
    except GitError:
        return RmRisk(repo=entry.repo, short_name=spec.name, has_uncommitted=True)

    unpushed = git_remote.count_commits_on_no_remote(worktree, entry.base)
    merged = _merged_into_base(worktree, entry.base) if unpushed > 0 else None
    return RmRisk(
        repo=entry.repo,
        short_name=spec.name,
        has_uncommitted=status.has_uncommitted,
        has_untracked=status.has_untracked,
        unpushed_commits=unpushed,
        no_upstream=unpushed > 0 and not status.upstream and merged is None,
        merged_upstream=merged,
    )


def _merged_into_base(worktree: Path, base: str) -> MergedSignal | None:
    """How the work in ``worktree`` already reached the remote copy of ``base``, if it did.

    Neither check proves the work is NOT merged when it says no; the caller
    then keeps treating the commits as unpushed.
    """

    upstream = git_remote.remote_copy_of_base(worktree, base)
    if upstream is None:
        return None
    if git_merged.cherry_unmerged(worktree, upstream) == 0:
        return "cherry"
    if git_merged.tree_contained_in(worktree, upstream):
        return "squash"
    return None
