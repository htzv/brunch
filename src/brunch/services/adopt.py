"""Service: retroactively adopt an existing folder of worktrees.

Given a directory whose direct children are git worktrees (created by hand
via ``git worktree add``), brunch reads each worktree's gitdir pointer to
find its canonical clone, reverse-resolves the canonical path against the
configured ``root`` to recover ``<forge>/<org>/<repo>``, reads the current
branch, and writes a ``brunch.toml`` describing the workspace. It then
runs ``sync`` and ``fsck`` to verify the adoption.

Notes on the ``base`` field. We considered using the branch's upstream-
tracking ref's short name to infer ``base``, but that's misleading: a
branch pushed with ``git push -u origin <name>`` ends up tracking
``origin/<name>``, which strips back to ``<name>`` — definitely not its
base. Adopt therefore writes ``base = "main"`` for every entry and the
rendered output asks the user to review and edit. Editing the manifest is
cheap; getting the inference wrong silently is not.

Adopt is intentionally conservative: any per-worktree error aborts the
whole adoption before ``brunch.toml`` is written, so we never leave a
partial manifest behind.
"""

from __future__ import annotations

import os
from pathlib import Path

from brunch import git
from brunch.errors import BrunchError, GitError
from brunch.manifest import write_workspace_manifest
from brunch.models import (
    AdoptError,
    AdoptOutcome,
    AdoptSkip,
    RepoEntry,
    RepoSpec,
    ToolConfig,
    WorkspaceLocation,
    WorkspaceManifest,
)
from brunch.paths import WORKSPACE_MARKER, expand_root
from brunch.services.fsck import fsck_workspace
from brunch.services.sync import sync_workspace

DEFAULT_BASE = "main"


def adopt_workspace(
    target: Path,
    *,
    name: str,
    config: ToolConfig,
    dry_run: bool = False,
) -> AdoptOutcome:
    """Adopt the existing folder at ``target`` as a brunch workspace."""

    if not target.exists():
        raise BrunchError(
            f"target {target} does not exist",
            hint="point adopt at an existing directory that contains worktrees.",
        )
    if not target.is_dir():
        raise BrunchError(f"target {target} is not a directory")

    manifest_path = target / WORKSPACE_MARKER
    if manifest_path.exists():
        raise BrunchError(
            f"{manifest_path} already exists",
            hint=(
                "this directory is already a brunch workspace; nothing to adopt. "
                "Use `brunch sync` or `brunch fsck` to verify it."
            ),
        )

    discovered: list[RepoEntry] = []
    skipped: list[AdoptSkip] = []
    errors: list[AdoptError] = []
    seen_short_names: set[str] = set()

    for entry_path in _iter_direct_children(target):
        if not entry_path.is_dir():
            continue
        git_marker = entry_path / ".git"
        if not git_marker.exists():
            # Not a git tree — leave it alone (will be preserved by `rm` too).
            continue
        if git_marker.is_dir():
            skipped.append(
                AdoptSkip(
                    path=entry_path,
                    reason="regular git clone (not a worktree)",
                )
            )
            continue

        # `.git` is a file → this is a worktree. Resolve its canonical.
        try:
            canonical = _read_gitdir_canonical(git_marker)
        except BrunchError as e:
            errors.append(AdoptError(path=entry_path, message=str(e), hint=e.hint))
            continue

        try:
            spec = _reverse_resolve(canonical, config.root)
        except BrunchError as e:
            errors.append(AdoptError(path=entry_path, message=str(e), hint=e.hint))
            continue

        try:
            branch = git.current_branch(entry_path)
        except GitError as e:
            errors.append(AdoptError(path=entry_path, message=str(e)))
            continue
        if branch is None:
            errors.append(
                AdoptError(
                    path=entry_path,
                    message="worktree is in detached HEAD; cannot infer a branch",
                    hint="check out a named branch in the worktree, then retry adopt.",
                )
            )
            continue

        if spec.name in seen_short_names:
            errors.append(
                AdoptError(
                    path=entry_path,
                    message=(
                        f"two worktrees resolve to the same short name "
                        f"{spec.name!r}; brunch can't address them both."
                    ),
                    hint=(
                        "rename one of the subdirectories, or remove the duplicate before adopting."
                    ),
                )
            )
            continue
        seen_short_names.add(spec.name)

        repo_string = spec.short if spec.forge == config.default_forge else spec.qualified
        discovered.append(RepoEntry(repo=repo_string, branch=branch, base=DEFAULT_BASE))

    if errors:
        return AdoptOutcome(
            name=name,
            path=target,
            action="failed",
            discovered=discovered,
            skipped=skipped,
            errors=errors,
            dry_run=dry_run,
        )

    if not discovered:
        raise BrunchError(
            f"no worktrees found under {target}; nothing to adopt",
            hint=(
                "adopt expects direct child directories that are git worktrees "
                "(i.e. created with `git worktree add`). If you have regular "
                "clones instead, create a workspace with `brunch init` and "
                "`brunch add` instead."
            ),
        )

    if dry_run:
        return AdoptOutcome(
            name=name,
            path=target,
            action="would_adopt",
            discovered=discovered,
            skipped=skipped,
            errors=[],
            dry_run=True,
        )

    manifest = WorkspaceManifest(name=name, repo=discovered)
    write_workspace_manifest(manifest_path, manifest)

    location = WorkspaceLocation(mode="workspace", root=target, manifest_path=manifest_path)
    sync_report = sync_workspace(location, config)
    fsck_report = fsck_workspace(location, config)

    return AdoptOutcome(
        name=name,
        path=target,
        action="adopted",
        discovered=discovered,
        skipped=skipped,
        errors=[],
        sync_report=sync_report,
        fsck_report=fsck_report,
    )


# ---------------------------------------------------------------------------
# Helpers


def _iter_direct_children(target: Path) -> list[Path]:
    """Direct children of ``target``, sorted by name, no symlink-following."""

    try:
        with os.scandir(target) as it:
            entries = sorted(it, key=lambda e: e.name)
    except OSError:
        return []
    return [Path(e.path) for e in entries]


def _read_gitdir_canonical(git_file: Path) -> Path:
    """Parse a worktree ``.git`` file and return its canonical clone path.

    The file contains ``gitdir: <abs-path>``; that path is
    ``<canonical>/.git/worktrees/<worktree-id>``, so the canonical sits
    three parents up.
    """

    try:
        content = git_file.read_text(encoding="utf-8").strip()
    except OSError as e:
        raise BrunchError(f"failed to read {git_file}: {e}") from e

    if not content.startswith("gitdir:"):
        raise BrunchError(
            f"{git_file} is not a worktree marker (missing 'gitdir:' prefix)",
        )

    gitdir = Path(content.removeprefix("gitdir:").strip())
    # Resolve relative gitdirs against the .git file's directory.
    if not gitdir.is_absolute():
        gitdir = (git_file.parent / gitdir).resolve()

    if not gitdir.exists():
        raise BrunchError(
            f"gitdir target {gitdir} does not exist (worktree may be broken)",
            hint=f"try `git -C {gitdir.parent.parent.parent} worktree repair`",
        )

    if gitdir.parent.name != "worktrees" or gitdir.parent.parent.name != ".git":
        raise BrunchError(
            f"unexpected gitdir layout: {gitdir} (expected <canonical>/.git/worktrees/<id>)"
        )

    return gitdir.parent.parent.parent.resolve()


def _reverse_resolve(canonical: Path, root: Path) -> RepoSpec:
    """Recover ``<forge>/<org>/<repo>`` from a canonical clone path.

    Expects the canonical to sit at exactly ``<root>/<forge>/<org>/<repo>``.
    Anything else (clones outside root, off-pattern paths) raises with a
    clear remediation hint.
    """

    expanded_root = expand_root(root).resolve()
    try:
        rel = canonical.relative_to(expanded_root)
    except ValueError as e:
        raise BrunchError(
            f"canonical clone at {canonical} is not under the configured "
            f"root {expanded_root}; can't reverse-resolve <forge>/<org>/<repo>",
            hint=(
                f"either set `root` in ~/.config/brunch/config.toml to point at "
                f"a parent of {canonical}, or move the canonical clone into the "
                "configured root with the ghq-style layout."
            ),
        ) from e

    parts = rel.parts
    if len(parts) != 3:
        raise BrunchError(
            f"canonical {canonical} relative to root {expanded_root} has "
            f"{len(parts)} path component(s); expected exactly "
            "<forge>/<org>/<repo>",
            hint=("move the canonical clone so it lives at <root>/<forge>/<org>/<repo>."),
        )

    forge, org, name = parts
    return RepoSpec(forge=forge, org=org, name=name)
