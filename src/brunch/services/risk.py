"""Is it safe to remove a repo's worktree? The one answer `br rm` and `br drop` share.

A worktree is at risk when removing it could lose work: uncommitted changes,
untracked files, or commits that exist nowhere else.
"""

from __future__ import annotations

from pathlib import Path

from brunch import git, git_remote
from brunch.errors import GitError, RepoSpecError
from brunch.models import RepoEntry, RmRisk, ToolConfig
from brunch.paths import parse_repo_spec


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

    if status.upstream:
        unpushed = status.ahead
        no_upstream = False
    else:
        unpushed = git_remote.count_unpublished_commits(worktree, entry.base)
        no_upstream = unpushed > 0

    return RmRisk(
        repo=entry.repo,
        short_name=spec.name,
        has_uncommitted=status.has_uncommitted,
        has_untracked=status.has_untracked,
        unpushed_commits=unpushed,
        no_upstream=no_upstream,
    )
