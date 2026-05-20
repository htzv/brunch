"""Service: per-repo fetch + rebase across a workspace.

The rebase semantics are documented in ``docs/initial-design.md §7.4``:

- For each repo, unless ``--no-fetch``: ``git fetch`` from the default remote.
- Rebase target is ``origin/<base>`` if that remote-tracking ref exists,
  otherwise the local ``<base>``. ``--onto <branch>`` overrides target.
- Default behaviour stops on the first conflict; ``--continue-on-error``
  fans out across all repos and aggregates the result.
- ``--autostash`` is passed through to ``git rebase``.
"""

from __future__ import annotations

from pathlib import Path

from brunch import git
from brunch.errors import GitError, RepoSpecError, WorkspaceNotFoundError
from brunch.manifest import load_workspace_manifest
from brunch.models import (
    RebaseAction,
    RebaseReport,
    RepoEntry,
    ToolConfig,
    WorkspaceLocation,
)
from brunch.paths import parse_repo_spec


def rebase_workspace(
    location: WorkspaceLocation,
    config: ToolConfig,
    *,
    onto: str | None = None,
    autostash: bool = False,
    no_fetch: bool = False,
    continue_on_error: bool = False,
    dry_run: bool = False,
) -> RebaseReport:
    """Run a rebase pass across the workspace."""

    if location.mode != "workspace":
        raise WorkspaceNotFoundError(
            f"rebase at set roots isn't supported yet (got mode={location.mode!r})",
            hint="cd into one of the child workspaces, or pass -w <path>.",
        )

    manifest = load_workspace_manifest(location.manifest_path)
    actions: list[RebaseAction] = []
    stop = False

    for entry in manifest.repos:
        if stop:
            actions.append(
                RebaseAction(
                    repo=entry.repo,
                    short_name=entry.repo.split("/")[-1],
                    action="skipped",
                    target=onto or entry.base,
                    message="skipped after earlier conflict (rerun with --continue-on-error)",
                )
            )
            continue
        action = _rebase_one(
            entry,
            location.root,
            config,
            onto=onto,
            autostash=autostash,
            no_fetch=no_fetch,
            dry_run=dry_run,
        )
        actions.append(action)
        if action.action == "conflict" and not continue_on_error:
            stop = True

    return RebaseReport(
        workspace_name=manifest.name,
        workspace_path=location.root,
        actions=actions,
        dry_run=dry_run,
    )


def _rebase_one(
    entry: RepoEntry,
    workspace_root: Path,
    config: ToolConfig,
    *,
    onto: str | None,
    autostash: bool,
    no_fetch: bool,
    dry_run: bool,
) -> RebaseAction:
    try:
        spec = parse_repo_spec(entry.repo, default_forge=config.default_forge)
    except RepoSpecError as e:
        return RebaseAction(
            repo=entry.repo,
            short_name=entry.repo,
            action="error",
            target=onto or entry.base,
            message=str(e),
            hint=e.hint,
        )

    worktree = workspace_root / spec.name
    if not worktree.exists() or not git.is_git_repo(worktree):
        return RebaseAction(
            repo=entry.repo,
            short_name=spec.name,
            action="skipped",
            target=onto or entry.base,
            message=f"worktree missing at {worktree}",
            hint="run `brunch sync` first",
        )

    # Decide on the rebase target.
    if onto is not None:
        target = onto
        upstream: str | None = entry.base
    else:
        if not no_fetch and git.has_remote(worktree):
            try:
                git.fetch(worktree)
            except GitError as e:
                return RebaseAction(
                    repo=entry.repo,
                    short_name=spec.name,
                    action="error",
                    target=entry.base,
                    message=f"fetch failed: {e}",
                )

        if git.rev_parse_verify(worktree, f"origin/{entry.base}"):
            target = f"origin/{entry.base}"
        else:
            target = entry.base
        upstream = None

    if dry_run:
        return RebaseAction(
            repo=entry.repo,
            short_name=spec.name,
            action="would_rebase",
            target=target,
            message=f"would rebase onto {target}",
        )

    # Check if the rebase would be a no-op: the current branch already
    # contains the target. `git merge-base --is-ancestor` answers this.
    if _is_up_to_date(worktree, target):
        return RebaseAction(
            repo=entry.repo,
            short_name=spec.name,
            action="up_to_date",
            target=target,
            message=f"already up to date with {target}",
        )

    try:
        git.rebase(worktree, target, upstream=upstream, autostash=autostash)
    except GitError as e:
        if git.rebase_in_progress(worktree):
            return RebaseAction(
                repo=entry.repo,
                short_name=spec.name,
                action="conflict",
                target=target,
                message=str(e),
                hint=(
                    f"resolve conflicts in {worktree}, then `git rebase --continue`. "
                    "Use `git rebase --abort` to roll back."
                ),
            )
        return RebaseAction(
            repo=entry.repo,
            short_name=spec.name,
            action="error",
            target=target,
            message=str(e),
        )

    return RebaseAction(
        repo=entry.repo,
        short_name=spec.name,
        action="rebased",
        target=target,
        message=f"rebased onto {target}",
    )


def _is_up_to_date(worktree: Path, target: str) -> bool:
    """True if HEAD already contains target (rebase would be a no-op)."""

    # We need `target` to be a parent of HEAD. `git merge-base --is-ancestor
    # <target> HEAD` returns 0 iff target is an ancestor.
    from brunch.git import _run

    result = _run(
        ["merge-base", "--is-ancestor", target, "HEAD"],
        cwd=worktree,
        check=False,
    )
    return result.returncode == 0
