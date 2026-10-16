"""Where a new branch starts: the one rule `br add`, `br sync` and `br init -t` share.

Fetch the remote (and prune it), then follow git's own rule: a branch that the
remote already has is taken from it and tracks it; any other new branch starts
from the remote's copy of its base and tracks nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from brunch import git_remote
from brunch.errors import BranchConflictError, RemoteError


@dataclass(frozen=True)
class BranchStart:
    """What was decided about a new branch's start."""

    remote: str | None
    """The remote chosen; None when the repo has none (or none could be chosen offline)."""
    base: str
    """The base branch: the one given, else the remote's default branch."""
    start_point: str
    fetched: bool
    """The remote was fetched (with ``dry_run``: would be)."""
    tracks: str | None
    """The remote branch of the same name the new branch is taken from and tracks."""


def plan_branch_start(
    canonical: Path,
    *,
    branch: str,
    base: str | None,
    base_was_given: bool,
    requested_remote: str | None,
    fetch: bool,
    dry_run: bool,
) -> BranchStart:
    """Fetch if asked to, and decide the start point for a new ``branch``.

    ``base`` is None when there is none: it then becomes the remote's default
    branch (``main`` when that is unknown). ``base_was_given`` says the person
    chose the base; that is an error when the remote already has the branch,
    since the base would be ignored (a base recorded in ``brunch.toml`` is not
    a choice made now). Raises ``FetchError`` or ``RemoteError`` before anything
    is created.
    """

    remote = _choose_remote(canonical, requested_remote, fetch=fetch)
    if remote is None or not fetch:
        effective_base = base or _default_base(canonical, remote)
        return BranchStart(
            remote=remote,
            base=effective_base,
            start_point=effective_base,
            fetched=False,
            tracks=None,
        )

    if not dry_run:
        # Prune, so a remote branch deleted since the last fetch is not followed.
        git_remote.fetch_remote(canonical, remote, prune=True)
    # After the fetch: it creates `<remote>/HEAD` when the clone has none yet.
    effective_base = base or _default_base(canonical, remote)
    tracks = git_remote.remote_branch_ref(canonical, remote, branch)
    if tracks is not None:
        _refuse_explicit_base(remote, branch, base if base_was_given else None)
        return BranchStart(
            remote=remote, base=effective_base, start_point=tracks, fetched=True, tracks=tracks
        )
    start_point = git_remote.resolve_start_point(canonical, remote, effective_base)
    return BranchStart(
        remote=remote, base=effective_base, start_point=start_point, fetched=True, tracks=None
    )


def _default_base(canonical: Path, remote: str | None) -> str:
    """The remote's default branch as the clone last saw it, else ``main``."""

    if remote is None:
        return git_remote.FALLBACK_DEFAULT_BRANCH
    return git_remote.default_branch(canonical, remote)


def _choose_remote(canonical: Path, requested: str | None, *, fetch: bool) -> str | None:
    """The remote to fetch and branch from.

    With ``fetch`` off, nothing depends on the remote, so an ambiguous choice is
    not an error; the remote is then only reported when it can be determined.
    """

    try:
        return git_remote.resolve_remote(canonical, requested)
    except RemoteError:
        if fetch or requested is not None:
            raise
        return None


def _refuse_explicit_base(remote: str, branch: str, base: str | None) -> None:
    """A branch taken from its remote branch has no use for ``--base``."""

    if base is not None:
        raise BranchConflictError(
            f"branch {branch!r} already exists on {remote!r}, so --base {base!r} would be ignored",
            hint=(
                "drop --base to take the branch from the remote and track it, "
                "or pick another name with --branch"
            ),
        )
