"""Service: add a repo to a workspace and materialise its worktree."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from brunch import git, git_remote
from brunch.errors import (
    BranchConflictError,
    BrunchError,
    DuplicateRepoError,
    GitError,
    RemoteError,
    WorkspaceNotFoundError,
)
from brunch.manifest import load_workspace_manifest, write_workspace_manifest
from brunch.models import (
    AddOutcome,
    RepoEntry,
    ToolConfig,
    WorkspaceLocation,
    WorkspaceManifest,
)
from brunch.paths import canonical_clone_path, parse_repo_spec


def add_repo(
    location: WorkspaceLocation,
    config: ToolConfig,
    *,
    repo: str,
    branch: str | None = None,
    base: str = "main",
    remote: str | None = None,
    fetch: bool = True,
    dry_run: bool = False,
) -> AddOutcome:
    """Add a [[repo]] entry and create its worktree.

    ``branch`` defaults to the workspace name (matches the template-default
    convention). ``base`` defaults to ``"main"``. Both can be overridden.

    Unless ``fetch`` is False, the chosen remote is fetched first and a new
    branch starts from its copy of ``base``. A failed fetch, or an unusable
    ``remote``, stops everything before anything is created.
    """

    if location.mode != "workspace":
        raise WorkspaceNotFoundError(
            f"add only works inside a workspace (got mode={location.mode!r})",
            hint="cd into a workspace, or pass -w <path>.",
        )

    manifest = load_workspace_manifest(location.manifest_path)
    effective_branch = branch or manifest.name

    if any(r.repo == repo for r in manifest.repos):
        raise DuplicateRepoError(
            f"repo {repo!r} is already in the manifest at {location.manifest_path}",
            hint="edit the entry directly, or remove it first.",
        )

    spec = parse_repo_spec(repo, default_forge=config.default_forge)
    canonical = canonical_clone_path(spec, root=config.root)
    if not canonical.exists():
        raise BrunchError(
            f"canonical clone not found at {canonical}",
            hint=f"clone it: `gh repo clone {spec.short} {canonical}` (or via ghq)",
        )
    if not git.is_git_repo(canonical):
        raise GitError(f"{canonical} exists but is not a git repository")

    # Check short_name collision in the manifest before touching the filesystem.
    if any(name == spec.name for name in _existing_short_names(manifest, config)):
        raise DuplicateRepoError(
            f"a different repo with short name {spec.name!r} is already in the manifest",
            hint="rename the existing entry or pick a different repo.",
        )

    worktree_path = location.root / spec.name
    if worktree_path.exists():
        raise BrunchError(
            f"target {worktree_path} already exists",
            hint="remove it first, or pick a different repo name.",
        )

    # Pre-flight: branch already checked out in another worktree of this canonical?
    for ref in git.worktree_list(canonical):
        if ref.branch == effective_branch and ref.path != worktree_path:
            raise BranchConflictError(
                f"branch {effective_branch!r} is already checked out at {ref.path}",
                hint=(
                    "pick a different branch with --branch, or remove the existing worktree first."
                ),
            )

    _refuse_existing_branch(canonical, effective_branch, base)

    chosen_remote = _choose_remote(canonical, remote, fetch=fetch)
    will_fetch = fetch and chosen_remote is not None
    start_point = base
    if chosen_remote is not None and fetch:
        if not dry_run:
            git_remote.fetch_remote(canonical, chosen_remote)
            # A fetch can create local branches (a mirror-style refspec), so look again.
            _refuse_existing_branch(canonical, effective_branch, base)
        start_point = git_remote.resolve_start_point(canonical, chosen_remote, base)

    if dry_run:
        return AddOutcome(
            repo=repo,
            branch=effective_branch,
            base=base,
            worktree_path=worktree_path,
            dry_run=True,
            remote=chosen_remote,
            start_point=start_point,
            fetched=will_fetch,
        )

    git.add_worktree(canonical, worktree_path, branch=effective_branch, start_point=start_point)
    manifest.repos.append(RepoEntry(repo=repo, branch=effective_branch, base=base))
    write_workspace_manifest(location.manifest_path, manifest)

    return AddOutcome(
        repo=repo,
        branch=effective_branch,
        base=base,
        worktree_path=worktree_path,
        remote=chosen_remote,
        start_point=start_point,
        fetched=will_fetch,
    )


def _refuse_existing_branch(canonical: Path, branch: str, base: str) -> None:
    """Like `git checkout -b`: never silently reuse a branch and ignore ``base``."""

    if git.branch_exists(canonical, branch):
        raise BranchConflictError(
            f"branch {branch!r} already exists in {canonical}, so --base {base!r} would be ignored",
            hint=(
                "pick another name with --branch. If the branch is left over from a removed "
                f"workspace, delete it first: git -C {canonical} branch -d {branch}"
            ),
        )


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


def _existing_short_names(manifest: WorkspaceManifest, config: ToolConfig) -> Iterator[str]:
    """Yield the short_name of every entry whose repo parses cleanly."""

    for entry in manifest.repos:
        try:
            spec = parse_repo_spec(entry.repo, default_forge=config.default_forge)
        except Exception:
            continue
        yield spec.name
