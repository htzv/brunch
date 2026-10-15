"""`br rm` and `br drop` recognise work that was already merged upstream."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from brunch.cli import app
from tests.conftest import OriginRepo, _git

runner = CliRunner()
Setup = tuple[OriginRepo, Path, str]
BRANCH = "task-1"


def _work_on_branch(ws: Path, *, commits: int) -> Path:
    """Add the repo, make ``commits`` file commits, push the branch."""

    result = runner.invoke(app, ["add", "kybernetix/api", "-w", str(ws)])
    assert result.exit_code == 0, result.output
    worktree = ws / "api"
    for n in range(commits):
        _commit_file(worktree, f"work-{n}.txt", f"work {n}")
    _git(["push", "-u", "origin", BRANCH], cwd=worktree)
    return worktree


def _commit_file(repo: Path, name: str, message: str) -> None:
    (repo / name).write_text(f"{message}\n", encoding="utf-8")
    _git(["add", name], cwd=repo)
    _git(["commit", "-m", message], cwd=repo)


@pytest.fixture(params=["squash", "rebase"])
def merge_style(request: pytest.FixtureRequest) -> str:
    return str(request.param)


def _merge(origin: OriginRepo, style: str) -> None:
    (origin.squash_merge if style == "squash" else origin.rebase_merge)(BRANCH)


def _rm_dry_run(ws: Path, *extra: str) -> tuple[int, str]:
    result = runner.invoke(app, ["rm", "-w", str(ws), "--dry-run", *extra])
    return result.exit_code, result.output


class TestMergedWorkIsNotAtRisk:
    @pytest.mark.parametrize("commits", [1, 3])
    def test_rm_accepts_work_merged_by_either_style(
        self, stale_setup: Setup, merge_style: str, commits: int
    ) -> None:
        origin, ws, _ = stale_setup
        _work_on_branch(ws, commits=commits)
        _merge(origin, merge_style)

        code, output = _rm_dry_run(ws)

        assert code == 0, output
        assert "WOULD REMOVE" in output

    def test_the_output_says_why_the_repo_was_cleared(self, stale_setup: Setup) -> None:
        origin, ws, _ = stale_setup
        _work_on_branch(ws, commits=2)
        origin.squash_merge(BRANCH)

        _, output = _rm_dry_run(ws)

        assert "already merged" in output
        assert "squash" in output
        assert "api" in output

    def test_json_names_the_signal(self, stale_setup: Setup) -> None:
        origin, ws, _ = stale_setup
        _work_on_branch(ws, commits=2)
        origin.squash_merge(BRANCH)

        _, output = _rm_dry_run(ws, "--json")

        merged = json.loads(output)["merged"]
        assert [m["short_name"] for m in merged] == ["api"]
        assert merged[0]["merged_upstream"] == "squash"
        assert merged[0]["unpushed_commits"] == 2

    def test_a_single_commit_squash_or_a_rebase_is_reported_as_cherry(
        self, stale_setup: Setup
    ) -> None:
        origin, ws, _ = stale_setup
        _work_on_branch(ws, commits=2)
        origin.rebase_merge(BRANCH)

        _, output = _rm_dry_run(ws, "--json")

        assert json.loads(output)["merged"][0]["merged_upstream"] == "cherry"

    def test_drop_accepts_it_too_and_says_why(self, stale_setup: Setup, merge_style: str) -> None:
        origin, ws, _ = stale_setup
        _work_on_branch(ws, commits=2)
        _merge(origin, merge_style)

        result = runner.invoke(app, ["drop", "api", "-w", str(ws), "--dry-run"])

        assert result.exit_code == 0, result.output
        assert "already merged" in result.output

    def test_still_merged_after_main_moved_on(self, stale_setup: Setup) -> None:
        origin, ws, _ = stale_setup
        _work_on_branch(ws, commits=2)
        origin.squash_merge(BRANCH)
        origin.advance()

        code, output = _rm_dry_run(ws)

        assert code == 0, output

    def test_a_rebase_merge_is_still_recognised_after_main_edited_the_same_lines(
        self, stale_setup: Setup
    ) -> None:
        """The content check gives up on a conflict; the patch comparison does not."""

        origin, ws, _ = stale_setup
        _work_on_branch(ws, commits=2)
        origin.rebase_merge(BRANCH)
        origin.edit_main("work-0.txt", "main changed these lines afterwards\n")

        code, output = _rm_dry_run(ws, "--json")

        assert code == 0, output
        assert json.loads(output)["merged"][0]["merged_upstream"] == "cherry"

    def test_the_real_rm_removes_it(self, stale_setup: Setup) -> None:
        origin, ws, _ = stale_setup
        _work_on_branch(ws, commits=2)
        origin.squash_merge(BRANCH)

        result = runner.invoke(app, ["rm", "-w", str(ws)])

        assert result.exit_code == 0, result.output
        assert not ws.exists()


class TestStillAtRisk:
    def test_a_commit_made_after_the_merge_is_refused(
        self, stale_setup: Setup, merge_style: str
    ) -> None:
        origin, ws, _ = stale_setup
        worktree = _work_on_branch(ws, commits=2)
        _merge(origin, merge_style)
        _commit_file(worktree, "after-merge.txt", "work after the merge")

        code, output = _rm_dry_run(ws)

        assert code != 0
        assert "refused:" in output

    def test_uncommitted_changes_are_never_cleared_by_a_merge(self, stale_setup: Setup) -> None:
        origin, ws, _ = stale_setup
        worktree = _work_on_branch(ws, commits=2)
        origin.squash_merge(BRANCH)
        (worktree / "work-0.txt").write_text("edited after\n", encoding="utf-8")

        code, output = _rm_dry_run(ws)

        assert code != 0
        assert "uncommitted" in output

    def test_untracked_files_are_never_cleared_by_a_merge(self, stale_setup: Setup) -> None:
        origin, ws, _ = stale_setup
        worktree = _work_on_branch(ws, commits=2)
        origin.squash_merge(BRANCH)
        (worktree / "scratch.txt").write_text("x\n", encoding="utf-8")

        code, output = _rm_dry_run(ws)

        assert code != 0
        assert "untracked" in output

    def test_a_squash_that_main_later_edited_cannot_be_proven(self, stale_setup: Setup) -> None:
        origin, ws, _ = stale_setup
        _work_on_branch(ws, commits=2)
        origin.squash_merge(BRANCH)
        origin.edit_main("work-0.txt", "main changed these lines afterwards\n")

        code, output = _rm_dry_run(ws)

        assert code != 0
        assert "refused:" in output

    def test_unmerged_work_pushed_to_a_branch_is_not_reported_as_merged(
        self, stale_setup: Setup
    ) -> None:
        _, ws, _ = stale_setup
        _work_on_branch(ws, commits=2)

        code, output = _rm_dry_run(ws, "--json")

        assert code == 0
        assert json.loads(output)["merged"] == []

    def test_drop_refuses_work_added_after_the_merge(self, stale_setup: Setup) -> None:
        origin, ws, _ = stale_setup
        worktree = _work_on_branch(ws, commits=2)
        origin.squash_merge(BRANCH)
        _commit_file(worktree, "after-merge.txt", "work after the merge")

        result = runner.invoke(app, ["drop", "api", "-w", str(ws), "--dry-run"])

        assert result.exit_code != 0
        assert "refused to drop" in result.output


def test_an_unpushed_commit_that_changes_nothing_is_not_a_risk(stale_setup: Setup) -> None:
    """The check compares content: an empty commit has none to lose (the branch stays anyway)."""

    _, ws, _ = stale_setup
    result = runner.invoke(app, ["add", "kybernetix/api", "-w", str(ws)])
    assert result.exit_code == 0, result.output
    _git(["commit", "--allow-empty", "-m", "a note to self"], cwd=ws / "api")

    code, output = _rm_dry_run(ws, "--json")

    assert code == 0, output
    assert json.loads(output)["merged"][0]["unpushed_commits"] == 1


class TestMergedThenRevertedOnMain:
    """The work is in the remote's history, which is what git means by pushed.

    A merge commit followed by a revert already counts as pushed (the commits are
    reachable from main), so a patch that main has, then reverted, counts the
    same way; requiring the content to still be in main would treat the two
    differently, and would refuse a rebase merge once main edits the same lines.
    """

    def test_a_rebase_merge_that_main_later_reverted_is_still_recognised(
        self, stale_setup: Setup
    ) -> None:
        origin, ws, _ = stale_setup
        _work_on_branch(ws, commits=1)
        origin.rebase_merge(BRANCH)
        origin.revert_main()

        code, output = _rm_dry_run(ws, "--json")

        assert code == 0, output
        assert json.loads(output)["merged"][0]["merged_upstream"] == "cherry"

    def test_a_merge_commit_that_main_later_reverted_counts_as_pushed(
        self, stale_setup: Setup
    ) -> None:
        origin, ws, _ = stale_setup
        _work_on_branch(ws, commits=1)
        origin.merge_commit(BRANCH)
        origin.revert_main()

        code, output = _rm_dry_run(ws, "--json")

        assert code == 0, output
        assert json.loads(output)["risks"] == []
