"""Choosing a remote, fetching from it, and picking where a new branch starts.

These are the git facts brunch needs before it creates a worktree: which remote
to fetch, and whether the new branch should start from that remote's copy of the
base branch or from the local one.
"""

from __future__ import annotations

from pathlib import Path

from brunch.errors import FetchError, GitError, RemoteError
from brunch.git import rev_parse_verify, run_git

CONVENTIONAL_REMOTE = "origin"
FALLBACK_DEFAULT_BRANCH = "main"
DEFAULT_REMOTE_CONFIG_KEY = "checkout.defaultRemote"
USE_NO_FETCH_HINT = "Work offline with --no-fetch, which branches from the local base."


def remotes(path: Path) -> list[str]:
    """Names of the remotes configured in the repo at ``path``."""

    return run_git(["remote"], cwd=path).stdout.split()


def fetch_remote(path: Path, remote: str) -> None:
    """Run ``git fetch <remote>``; raise ``FetchError`` if it fails."""

    try:
        run_git(["fetch", remote], cwd=path)
    except GitError as e:
        raise FetchError(f"could not fetch {remote!r}: {e}", hint=USE_NO_FETCH_HINT) from e


def resolve_remote(path: Path, requested: str | None) -> str | None:
    """Choose the remote to fetch and branch from.

    Order: the ``requested`` name, then ``checkout.defaultRemote``, then the
    only remote, then the one named ``origin``. Returns ``None`` when the repo
    has no remotes and none was requested. Raises ``RemoteError`` when the
    choice is unknown or ambiguous.
    """

    available = remotes(path)
    if requested is not None:
        return _require_known(requested, available)

    configured = run_git(["config", "--get", DEFAULT_REMOTE_CONFIG_KEY], cwd=path, check=False)
    if configured.returncode == 0 and configured.stdout.strip():
        return _require_known(configured.stdout.strip(), available)

    if not available:
        return None
    if len(available) == 1:
        return available[0]
    if CONVENTIONAL_REMOTE in available:
        return CONVENTIONAL_REMOTE
    raise RemoteError(
        f"cannot tell which remote to use: {', '.join(available)}",
        hint="Pass --remote <name>, or run `git config checkout.defaultRemote <name>`.",
    )


def _require_known(name: str, available: list[str]) -> str:
    if name not in available:
        listed = ", ".join(available) if available else "none"
        raise RemoteError(f"no remote named {name!r} (remotes: {listed})")
    return name


def default_branch(path: Path, remote: str) -> str:
    """The remote's default branch, from ``<remote>/HEAD``; ``main`` if unknown."""

    result = run_git(
        ["symbolic-ref", "--short", f"refs/remotes/{remote}/HEAD"], cwd=path, check=False
    )
    prefix = f"{remote}/"
    target = result.stdout.strip()
    if result.returncode == 0 and target.startswith(prefix):
        return target.removeprefix(prefix)
    return FALLBACK_DEFAULT_BRANCH


def resolve_start_point(path: Path, remote: str | None, base: str) -> str:
    """The ref a new branch should start from.

    For the remote's default branch that is the remote copy (``origin/main``),
    which a fetch has just brought up to date, because the local ``main`` is
    usually stale. For any other base, such as the parent branch of a stack, it
    is the local branch when one exists, since it may hold commits that are not
    pushed. A base that is only on the remote, or is already a full ref such as
    ``origin/main``, is used as given.
    """

    if remote is None:
        return base
    remote_ref = f"{remote}/{base}"
    if base == default_branch(path, remote) and rev_parse_verify(
        path, f"refs/remotes/{remote_ref}"
    ):
        return remote_ref
    if rev_parse_verify(path, f"refs/heads/{base}"):
        return base
    if rev_parse_verify(path, f"refs/remotes/{remote_ref}"):
        return remote_ref
    return base
