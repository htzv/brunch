"""Service: compute aggregate workspace status.

Controllers call ``compute_workspace_status`` and render the returned
``WorkspaceStatus`` — they don't talk to git or parse manifests directly.
"""

from __future__ import annotations

from brunch import git
from brunch.errors import WorkspaceNotFoundError
from brunch.manifest import load_workspace_manifest
from brunch.models import (
    RepoStatus,
    ToolConfig,
    WorkspaceLocation,
    WorkspaceStatus,
)
from brunch.paths import parse_repo_spec


def compute_workspace_status(location: WorkspaceLocation, config: ToolConfig) -> WorkspaceStatus:
    """Build the status record for a workspace location."""

    if location.mode != "workspace":
        raise WorkspaceNotFoundError(
            f"status at set roots isn't supported in M1 (got mode={location.mode!r})",
            hint="cd into one of the child workspaces, or pass -w <path>.",
        )

    manifest = load_workspace_manifest(location.manifest_path)
    repos: list[RepoStatus] = []
    for entry in manifest.repos:
        spec = parse_repo_spec(entry.repo, default_forge=config.default_forge)
        worktree_path = location.root / spec.name

        if not worktree_path.exists() or not git.is_git_repo(worktree_path):
            repos.append(
                RepoStatus(
                    repo_spec=entry.repo,
                    short_name=spec.name,
                    worktree_path=worktree_path,
                    exists=False,
                    current_branch=None,
                    declared_branch=entry.branch,
                    declared_base=entry.base,
                    on_declared_branch=False,
                    ahead=0,
                    behind=0,
                    has_uncommitted=False,
                    has_untracked=False,
                )
            )
            continue

        st = git.get_status(worktree_path)
        repos.append(
            RepoStatus(
                repo_spec=entry.repo,
                short_name=spec.name,
                worktree_path=worktree_path,
                exists=True,
                current_branch=st.branch,
                declared_branch=entry.branch,
                declared_base=entry.base,
                on_declared_branch=(st.branch == entry.branch),
                ahead=st.ahead,
                behind=st.behind,
                has_uncommitted=st.has_uncommitted,
                has_untracked=st.has_untracked,
            )
        )

    return WorkspaceStatus(
        workspace_name=manifest.name,
        workspace_path=location.root,
        description=manifest.description,
        repos=repos,
    )
