"""Service: add a repo to a workspace and materialise its worktree."""

from __future__ import annotations

from brunch import git
from brunch.errors import (
    BranchConflictError,
    BrunchError,
    DuplicateRepoError,
    GitError,
    WorkspaceNotFoundError,
)
from brunch.manifest import load_workspace_manifest, write_workspace_manifest
from collections.abc import Iterator

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
    dry_run: bool = False,
) -> AddOutcome:
    """Add a [[repo]] entry and create its worktree.

    ``branch`` defaults to the workspace name (matches the template-default
    convention). ``base`` defaults to ``"main"``. Both can be overridden.
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

    if dry_run:
        return AddOutcome(
            repo=repo,
            branch=effective_branch,
            base=base,
            worktree_path=worktree_path,
            dry_run=True,
        )

    git.add_worktree(canonical, worktree_path, branch=effective_branch, base=base)
    manifest.repos.append(RepoEntry(repo=repo, branch=effective_branch, base=base))
    write_workspace_manifest(location.manifest_path, manifest)

    return AddOutcome(
        repo=repo,
        branch=effective_branch,
        base=base,
        worktree_path=worktree_path,
    )


def _existing_short_names(
    manifest: WorkspaceManifest, config: ToolConfig
) -> Iterator[str]:
    """Yield the short_name of every entry whose repo parses cleanly."""

    for entry in manifest.repos:
        try:
            spec = parse_repo_spec(entry.repo, default_forge=config.default_forge)
        except Exception:  # noqa: BLE001
            continue
        yield spec.name
