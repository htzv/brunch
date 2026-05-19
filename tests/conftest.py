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
