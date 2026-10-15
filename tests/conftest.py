"""Shared pytest fixtures for the brunch test suite.

The strategy throughout is to use real git in temp directories rather than
mocking git out: the per-repo state we depend on is git's, and faking it
would mostly verify that the fake matches our assumptions, not that the code
works against actual git.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest


# Set git author identity for the whole session so commits don't fail in
# environments where git's identity isn't configured (e.g. CI).
@pytest.fixture(autouse=True)
def _git_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_AUTHOR_NAME", "brunch-test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "brunch-test@example.invalid")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "brunch-test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "brunch-test@example.invalid")


def _git(args: list[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


@pytest.fixture
def make_canonical(tmp_path: Path) -> Callable[..., Path]:
    """Factory: create a fresh git repo with one initial commit on ``main``.

    Returned path is the working tree root, ready to be used as a "canonical
    clone" in brunch's sense (it has a `main` branch with a commit, so
    worktrees can branch off it).
    """

    counter = {"n": 0}

    def _make(name: str | None = None, *, initial_branch: str = "main") -> Path:
        counter["n"] += 1
        repo_name = name or f"repo-{counter['n']}"
        repo = tmp_path / "canonical" / repo_name
        repo.mkdir(parents=True)
        _git(["init", "-b", initial_branch], cwd=repo)
        (repo / "README.md").write_text(f"# {repo_name}\n", encoding="utf-8")
        _git(["add", "."], cwd=repo)
        _git(["commit", "-m", "initial commit"], cwd=repo)
        return repo

    return _make


@pytest.fixture
def make_workspace(tmp_path: Path) -> Callable[..., Path]:
    """Factory: create an empty workspace directory with a brunch.toml."""

    counter = {"n": 0}

    def _make(name: str | None = None, *, description: str | None = None) -> Path:
        counter["n"] += 1
        ws_name = name or f"ws-{counter['n']}"
        ws = tmp_path / "workspaces" / ws_name
        ws.mkdir(parents=True)
        content = f'name = "{ws_name}"\n'
        if description is not None:
            content += f'description = "{description}"\n'
        (ws / "brunch.toml").write_text(content, encoding="utf-8")
        return ws

    return _make


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point HOME and XDG paths at a fresh tmp directory.

    Useful when a test exercises config loading or archive paths and we want
    no leakage between the dev workstation and the test.
    """

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / ".local" / "share"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(home / ".cache"))
    # platformdirs caches lookups; clear them by forcing a fresh import path.
    yield home


def add_worktree(canonical: Path, target: Path, *, branch: str, base: str = "main") -> None:
    """Helper: run ``git worktree add -b <branch> <target> <base>`` against ``canonical``."""

    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "worktree", "add", "-b", branch, str(target), base],
        cwd=str(canonical),
        capture_output=True,
        text=True,
        check=True,
    )


@pytest.fixture
def worktree_factory() -> Callable[..., None]:
    """Expose :func:`add_worktree` as a fixture-friendly callable."""

    return add_worktree


# Ensure subprocess inherits a minimal, predictable environment by clearing
# any local git config that would otherwise leak in.
@pytest.fixture(autouse=True)
def _no_global_git_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "git-config-global"))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)


class OriginRepo:
    """A bare "origin" plus a canonical clone of it, as brunch's users have.

    ``canonical`` is a normal clone with ``origin`` configured and ``main``
    pushed. ``advance`` adds a commit to origin's branch from a second clone,
    so ``canonical`` falls behind without knowing it until it fetches.
    """

    def __init__(self, root: Path, name: str) -> None:
        self.bare = root / f"{name}.git"
        self.canonical = root / name
        self._pusher = root / f"{name}-pusher"
        self._advances = 0
        _git(["init", "--bare", "-b", "main", str(self.bare)])
        _git(["clone", str(self.bare), str(self._pusher)])
        (self._pusher / "README.md").write_text(f"# {name}\n", encoding="utf-8")
        _git(["add", "."], cwd=self._pusher)
        _git(["commit", "-m", "initial commit"], cwd=self._pusher)
        _git(["push", "origin", "HEAD:main"], cwd=self._pusher)
        _git(["clone", str(self.bare), str(self.canonical)])

    def advance(self, branch: str = "main") -> str:
        """Push one new commit to ``branch`` on origin; return its sha."""

        _git(["fetch", "origin"], cwd=self._pusher)
        _git(["checkout", "-B", branch, f"origin/{branch}"], cwd=self._pusher)
        self._advances += 1
        marker = self._pusher / f"change-{self._advances}.txt"
        marker.write_text("change\n", encoding="utf-8")
        _git(["add", "."], cwd=self._pusher)
        _git(["commit", "-m", f"advance {branch}"], cwd=self._pusher)
        _git(["push", "origin", f"HEAD:{branch}"], cwd=self._pusher)
        return _git(["rev-parse", "HEAD"], cwd=self._pusher).strip()

    def edit_main(self, filename: str, content: str) -> None:
        """Commit ``content`` to ``filename`` on origin's main."""

        _git(["fetch", "origin"], cwd=self._pusher)
        _git(["checkout", "-B", "main", "origin/main"], cwd=self._pusher)
        (self._pusher / filename).write_text(content, encoding="utf-8")
        _git(["commit", "-am", f"edit {filename}"], cwd=self._pusher)
        _git(["push", "origin", "HEAD:main"], cwd=self._pusher)

    def squash_merge(self, branch: str) -> None:
        """Squash-merge ``branch`` into main on origin, then delete ``branch`` there."""

        _git(["fetch", "origin"], cwd=self._pusher)
        _git(["checkout", "-B", "main", "origin/main"], cwd=self._pusher)
        _git(["merge", "--squash", f"origin/{branch}"], cwd=self._pusher)
        _git(["commit", "-m", f"squash {branch}"], cwd=self._pusher)
        _git(["push", "origin", "HEAD:main"], cwd=self._pusher)
        _git(["push", "origin", "--delete", branch], cwd=self._pusher)

    def rebase_merge(self, branch: str) -> None:
        """Rebase-merge ``branch`` into main on origin, then delete it.

        Main gets an unrelated commit first, so the replayed commits have a new
        parent and therefore new hashes, as a real rebase merge gives them.
        """

        _git(["fetch", "origin"], cwd=self._pusher)
        _git(["checkout", "-B", "main", "origin/main"], cwd=self._pusher)
        (self._pusher / "unrelated.txt").write_text("unrelated\n", encoding="utf-8")
        _git(["add", "unrelated.txt"], cwd=self._pusher)
        _git(["commit", "-m", "unrelated change on main"], cwd=self._pusher)
        _git(["cherry-pick", f"origin/main..origin/{branch}"], cwd=self._pusher)
        _git(["push", "origin", "HEAD:main"], cwd=self._pusher)
        _git(["push", "origin", "--delete", branch], cwd=self._pusher)

    def merge_commit(self, branch: str) -> None:
        """Merge ``branch`` into main on origin with a merge commit, then delete it."""

        _git(["fetch", "origin"], cwd=self._pusher)
        _git(["checkout", "-B", "main", "origin/main"], cwd=self._pusher)
        _git(["merge", "--no-ff", "-m", f"merge {branch}", f"origin/{branch}"], cwd=self._pusher)
        _git(["push", "origin", "HEAD:main"], cwd=self._pusher)
        _git(["push", "origin", "--delete", branch], cwd=self._pusher)

    def revert_main(self, count: int = 1) -> None:
        """Revert the last ``count`` commits (or the last merge commit) on origin's main."""

        _git(["fetch", "origin"], cwd=self._pusher)
        _git(["checkout", "-B", "main", "origin/main"], cwd=self._pusher)
        is_merge = len(_git(["rev-list", "--parents", "-n1", "HEAD"], cwd=self._pusher).split()) > 2
        if is_merge:
            _git(["revert", "--no-edit", "-m", "1", "HEAD"], cwd=self._pusher)
        else:
            _git(["revert", "--no-edit", f"HEAD~{count}..HEAD"], cwd=self._pusher)
        _git(["push", "origin", "HEAD:main"], cwd=self._pusher)

    def publish_branch(self, branch: str, *, from_ref: str = "main") -> None:
        """Create ``branch`` on origin at ``from_ref``."""

        _git(["fetch", "origin"], cwd=self._pusher)
        _git(["push", "origin", f"origin/{from_ref}:refs/heads/{branch}"], cwd=self._pusher)


@pytest.fixture
def make_origin(tmp_path: Path) -> Callable[..., OriginRepo]:
    """Factory: an :class:`OriginRepo` under a fresh directory."""

    counter = {"n": 0}

    def _make(name: str | None = None) -> OriginRepo:
        counter["n"] += 1
        root = tmp_path / "origins"
        root.mkdir(exist_ok=True)
        return OriginRepo(root, name or f"origin-repo-{counter['n']}")

    return _make
