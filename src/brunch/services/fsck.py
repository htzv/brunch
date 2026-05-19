"""Service: diagnose workspace health.

Returns a structured :class:`FsckReport`. The controller renders it. No
remediation happens here — ``--fix`` is parked for M5 (`brunch gc`).
"""

from __future__ import annotations

from pathlib import Path

from brunch import git
from brunch.errors import GitError, RepoSpecError, WorkspaceNotFoundError
from brunch.manifest import load_workspace_manifest
from brunch.models import (
    FsckFinding,
    FsckReport,
    RepoEntry,
    ToolConfig,
    WorkspaceLocation,
)
from brunch.paths import canonical_clone_path, parse_repo_spec


def fsck_workspace(location: WorkspaceLocation, config: ToolConfig) -> FsckReport:
    """Run all fsck checks against a workspace location."""

    if location.mode != "workspace":
        raise WorkspaceNotFoundError(
            f"fsck on set roots isn't supported in M1 (got mode={location.mode!r})",
            hint="cd into one of the child workspaces, or pass -w <path>.",
        )

    manifest = load_workspace_manifest(location.manifest_path)
    findings: list[FsckFinding] = []
    declared_paths: set[Path] = set()
    canonicals: dict[Path, list[str]] = {}

    for entry in manifest.repos:
        per_entry, canonical_used, worktree_path = _check_entry(entry, location, config)
        findings.extend(per_entry)
        if worktree_path is not None:
            declared_paths.add(worktree_path.resolve())
        if canonical_used is not None:
            canonicals.setdefault(canonical_used, []).append(entry.repo)

    findings.extend(_check_canonicals(canonicals))
    findings.extend(_check_extra_subdirs(location.root, declared_paths))

    return FsckReport(
        workspace_name=manifest.name,
        workspace_path=location.root,
        findings=findings,
    )


def _check_entry(
    entry: RepoEntry,
    location: WorkspaceLocation,
    config: ToolConfig,
) -> tuple[list[FsckFinding], Path | None, Path | None]:
    """Per-entry checks: canonical existence, worktree existence/health, drift.

    Returns ``(findings, canonical_path_or_None, worktree_path_or_None)``.
    The canonical path is only returned when it is usable (exists + is a
    repo) so callers can run canonical-wide checks against it.
    """

    out: list[FsckFinding] = []

    try:
        spec = parse_repo_spec(entry.repo, default_forge=config.default_forge)
    except RepoSpecError as e:
        out.append(
            FsckFinding(
                severity="error",
                code="repo-spec-invalid",
                repo=entry.repo,
                message=str(e),
                hint=e.hint,
            )
        )
        return out, None, None

    canonical = canonical_clone_path(spec, root=config.root)
    worktree = location.root / spec.name

    if not canonical.exists():
        out.append(
            FsckFinding(
                severity="error",
                code="canonical-missing",
                repo=entry.repo,
                message=f"canonical clone not found at {canonical}",
                hint=f"clone it: `gh repo clone {spec.short} {canonical}` (or via ghq)",
            )
        )
        return out, None, worktree
    if not git.is_git_repo(canonical):
        out.append(
            FsckFinding(
                severity="error",
                code="canonical-not-a-repo",
                repo=entry.repo,
                message=f"{canonical} exists but is not a git repository",
            )
        )
        return out, None, worktree

    if not worktree.exists():
        out.append(
            FsckFinding(
                severity="error",
                code="worktree-missing",
                repo=entry.repo,
                message=f"worktree missing at {worktree}",
                hint="run `brunch sync` to create it",
            )
        )
        return out, canonical, worktree
    if not git.is_git_repo(worktree):
        out.append(
            FsckFinding(
                severity="error",
                code="worktree-unhealthy",
                repo=entry.repo,
                message=f"worktree at {worktree} exists but git can't read it",
                hint=f"try `git -C {canonical} worktree repair`",
            )
        )
        return out, canonical, worktree

    try:
        actual_branch = git.current_branch(worktree)
    except GitError as e:
        out.append(
            FsckFinding(
                severity="error",
                code="worktree-unhealthy",
                repo=entry.repo,
                message=str(e),
            )
        )
        return out, canonical, worktree

    if actual_branch != entry.branch:
        out.append(
            FsckFinding(
                severity="warning",
                code="branch-drift",
                repo=entry.repo,
                message=(f"worktree is on {actual_branch!r}, manifest declares {entry.branch!r}"),
                hint="update the manifest, or switch the worktree branch deliberately",
            )
        )

    return out, canonical, worktree


def _check_canonicals(canonicals: dict[Path, list[str]]) -> list[FsckFinding]:
    """Canonical-wide checks: concurrent branch checkout, dangling refs."""

    out: list[FsckFinding] = []
    for canonical in canonicals:
        try:
            refs = git.worktree_list(canonical)
        except GitError:
            continue  # already reported during _check_entry

        branch_counts: dict[str, int] = {}
        for ref in refs:
            if ref.branch is not None:
                branch_counts[ref.branch] = branch_counts.get(ref.branch, 0) + 1
            if not ref.path.exists():
                out.append(
                    FsckFinding(
                        severity="warning",
                        code="dangling-worktree-ref",
                        message=(
                            f"canonical {canonical} has a worktree ref at "
                            f"{ref.path} but the path no longer exists"
                        ),
                        hint=f"run `git -C {canonical} worktree prune`",
                    )
                )

        for branch, count in branch_counts.items():
            if count > 1:
                out.append(
                    FsckFinding(
                        severity="warning",
                        code="branch-concurrent-checkout",
                        message=(f"branch {branch!r} appears in {count} worktrees of {canonical}"),
                    )
                )
    return out


def _check_extra_subdirs(workspace_root: Path, declared_paths: set[Path]) -> list[FsckFinding]:
    """Flag subdirs of the workspace that look like worktrees but aren't declared."""

    out: list[FsckFinding] = []
    if not workspace_root.is_dir():
        return out
    for child in sorted(workspace_root.iterdir()):
        if not child.is_dir():
            continue
        if child.resolve() in declared_paths:
            continue
        marker = child / ".git"
        if marker.exists():
            out.append(
                FsckFinding(
                    severity="warning",
                    code="extra-worktree",
                    message=(
                        f"subdirectory {child.name!r} looks like a worktree "
                        f"but is not in the manifest"
                    ),
                    hint="add it with `brunch add` or remove it",
                )
            )
    return out
