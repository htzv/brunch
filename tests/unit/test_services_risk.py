"""What makes a repo's worktree unsafe to remove, whichever command asks.

`br rm` and `br drop` assess the same way; every case runs against both.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from brunch.models import RepoEntry, RmRisk, ToolConfig
from brunch.services import drop, rm
from tests.conftest import OriginRepo, _git

Assess = Callable[[RepoEntry, Path, ToolConfig], RmRisk]
ASSESSORS: list[Assess] = [rm._assess_one, drop._assess]
CONFIG = ToolConfig(default_forge="github.com")
REPO = "kybernetix/api"
ENTRY = RepoEntry(repo=REPO, branch="feat", base="main")

pytestmark = pytest.mark.parametrize("assess", ASSESSORS, ids=["rm", "drop"])


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    return root


def _worktree(canonical: Path, workspace: Path, *, start: str = "main") -> Path:
    target = workspace / "api"
    subprocess.run(
        ["git", "worktree", "add", "--no-track", "-b", "feat", str(target), start],
        cwd=canonical,
        check=True,
        capture_output=True,
    )
    return target


def test_clean_worktree_is_not_at_risk(
    assess: Assess, make_canonical: Callable[..., Path], workspace: Path
) -> None:
    _worktree(make_canonical(), workspace)
    risk = assess(ENTRY, workspace, CONFIG)
    assert not risk.is_at_risk
    assert risk.short_name == "api"


def test_uncommitted_change_is_at_risk(
    assess: Assess, make_canonical: Callable[..., Path], workspace: Path
) -> None:
    wt = _worktree(make_canonical(), workspace)
    (wt / "README.md").write_text("changed\n", encoding="utf-8")
    risk = assess(ENTRY, workspace, CONFIG)
    assert risk.has_uncommitted
    assert risk.is_at_risk


def test_untracked_file_is_at_risk(
    assess: Assess, make_canonical: Callable[..., Path], workspace: Path
) -> None:
    wt = _worktree(make_canonical(), workspace)
    (wt / "new.txt").write_text("x\n", encoding="utf-8")
    risk = assess(ENTRY, workspace, CONFIG)
    assert risk.has_untracked
    assert not risk.has_uncommitted


def test_commit_on_a_branch_without_upstream_is_at_risk(
    assess: Assess, make_canonical: Callable[..., Path], workspace: Path
) -> None:
    wt = _worktree(make_canonical(), workspace)
    _git(["commit", "--allow-empty", "-m", "mine"], cwd=wt)
    risk = assess(ENTRY, workspace, CONFIG)
    assert risk.no_upstream
    assert risk.unpushed_commits == 1


def test_branch_without_upstream_and_without_new_commits_is_not_at_risk(
    assess: Assess, make_canonical: Callable[..., Path], workspace: Path
) -> None:
    _worktree(make_canonical(), workspace)
    risk = assess(ENTRY, workspace, CONFIG)
    assert not risk.no_upstream
    assert risk.unpushed_commits == 0


def test_commit_ahead_of_an_upstream_counts_as_unpushed(
    assess: Assess, make_origin: Callable[..., OriginRepo], workspace: Path
) -> None:
    origin = make_origin()
    wt = workspace / "api"
    _git(["worktree", "add", "-b", "feat", str(wt), "origin/main"], cwd=origin.canonical)
    _git(["commit", "--allow-empty", "-m", "mine"], cwd=wt)
    risk = assess(ENTRY, workspace, CONFIG)
    assert risk.unpushed_commits == 1
    assert not risk.no_upstream


def test_pushed_work_is_not_at_risk(
    assess: Assess, make_origin: Callable[..., OriginRepo], workspace: Path
) -> None:
    origin = make_origin()
    wt = workspace / "api"
    _git(["worktree", "add", "-b", "feat", str(wt), "origin/main"], cwd=origin.canonical)
    _git(["commit", "--allow-empty", "-m", "mine"], cwd=wt)
    _git(["push", "-u", "origin", "feat"], cwd=wt)
    assert not assess(ENTRY, workspace, CONFIG).is_at_risk


def test_missing_worktree_is_not_at_risk(assess: Assess, workspace: Path) -> None:
    assert not assess(ENTRY, workspace, CONFIG).is_at_risk


def test_directory_that_is_not_a_git_repo_is_not_at_risk(assess: Assess, workspace: Path) -> None:
    (workspace / "api").mkdir()
    assert not assess(ENTRY, workspace, CONFIG).is_at_risk


def test_unparseable_repo_spec_is_not_at_risk_and_keeps_the_spec_as_its_name(
    assess: Assess, workspace: Path
) -> None:
    entry = RepoEntry(repo="not a repo spec", branch="feat", base="main")
    risk = assess(entry, workspace, CONFIG)
    assert not risk.is_at_risk
    assert risk.short_name == "not a repo spec"
