"""`br rm` and `br drop` ask git whether work is pushed anywhere, on fresh remote refs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from brunch import git_remote
from brunch.cli import app
from tests.conftest import OriginRepo, _git

runner = CliRunner()
Setup = tuple[OriginRepo, Path, str]


def _add(ws: Path, *extra: str) -> Path:
    result = runner.invoke(app, ["add", "kybernetix/api", "-w", str(ws), *extra])
    assert result.exit_code == 0, result.output
    return ws / "api"


def _commit(repo: Path, message: str) -> None:
    """A commit that changes something: an empty one has nothing to lose."""

    name = f"{message.replace(' ', '-')}.txt"
    (repo / name).write_text(f"{message}\n", encoding="utf-8")
    _git(["add", name], cwd=repo)
    _git(["commit", "-m", message], cwd=repo)


class TestCodeReviewFlow:
    """Pull someone's branch into an untracked branch, then clean up."""

    def _pulled_pr_branch(self, setup: Setup) -> Path:
        origin, ws, _ = setup
        origin.publish_branch("pr-branch")
        origin.advance("pr-branch")
        origin.advance("pr-branch")
        # --no-fetch: the branch starts untracked from main, as it did before `br add`
        # learned to take the remote branch; then pull it by name, as a reviewer would.
        worktree = _add(ws, "--branch", "pr-branch", "--no-fetch")
        _git(["pull", "origin", "pr-branch"], cwd=worktree)
        return ws

    def test_rm_is_not_refused(self, stale_setup: Setup) -> None:
        ws = self._pulled_pr_branch(stale_setup)
        result = runner.invoke(app, ["rm", "-w", str(ws), "--dry-run"])
        assert result.exit_code == 0, result.output
        assert "refused:" not in result.output
        assert "WOULD REMOVE" in result.output

    def test_drop_is_not_refused(self, stale_setup: Setup) -> None:
        ws = self._pulled_pr_branch(stale_setup)
        result = runner.invoke(app, ["drop", "api", "-w", str(ws), "--dry-run"])
        assert result.exit_code == 0, result.output
        assert "refused to drop" not in result.output
        assert "would drop" in result.output

    def test_a_commit_of_your_own_on_top_is_still_refused(self, stale_setup: Setup) -> None:
        ws = self._pulled_pr_branch(stale_setup)
        _commit(ws / "api", "my review fix")
        result = runner.invoke(app, ["rm", "-w", str(ws), "--dry-run"])
        assert result.exit_code != 0
        assert "1 local-only commit" in result.output


class TestDeletedRemoteBranch:
    def _pushed_with_late_commit(self, setup: Setup) -> tuple[Path, Path]:
        _, ws, _ = setup
        worktree = _add(ws)
        _commit(worktree, "pushed work")
        _git(["push", "-u", "origin", "task-1"], cwd=worktree)
        _commit(worktree, "late work, never pushed")
        return ws, worktree

    def test_a_pushed_branch_that_the_remote_deleted_still_shows_unpushed_work(
        self, stale_setup: Setup
    ) -> None:
        """After a pruning fetch git omits `ahead`; the check must not rely on it."""

        origin, _, _ = stale_setup
        ws, _ = self._pushed_with_late_commit(stale_setup)
        _git(["push", "origin", "--delete", "task-1"], cwd=origin.canonical)

        result = runner.invoke(app, ["rm", "-w", str(ws), "--dry-run"])

        assert result.exit_code != 0
        assert "refused:" in result.output

    def test_a_branch_the_remote_deleted_unmerged_is_flagged_after_the_prune(
        self, stale_setup: Setup
    ) -> None:
        origin, ws, _ = stale_setup
        worktree = _add(ws)
        _commit(worktree, "only ever pushed to a branch that is now gone")
        _git(["push", "-u", "origin", "task-1"], cwd=worktree)
        _git(["branch", "-D", "task-1"], cwd=origin.bare)

        result = runner.invoke(app, ["rm", "-w", str(ws), "--dry-run"])

        assert result.exit_code != 0
        assert "1 unpushed commit" in result.output

    def test_no_fetch_trusts_the_remote_refs_already_there(self, stale_setup: Setup) -> None:
        """The price of working offline: a remote branch deleted meanwhile still reads as pushed."""

        origin, ws, _ = stale_setup
        worktree = _add(ws)
        _commit(worktree, "pushed once")
        _git(["push", "-u", "origin", "task-1"], cwd=worktree)
        _git(["branch", "-D", "task-1"], cwd=origin.bare)

        result = runner.invoke(app, ["rm", "-w", str(ws), "--dry-run", "--no-fetch"])

        assert result.exit_code == 0, result.output


class TestFetchBeforeJudging:
    def test_dry_run_fetches_too(self, stale_setup: Setup) -> None:
        origin, ws, new_tip = stale_setup
        _add(ws, "--no-fetch")
        stale = _git(["rev-parse", "origin/main"], cwd=origin.canonical).strip()
        assert stale != new_tip

        runner.invoke(app, ["rm", "-w", str(ws), "--dry-run"])

        assert _git(["rev-parse", "origin/main"], cwd=origin.canonical).strip() == new_tip

    def test_no_fetch_leaves_the_remote_refs_alone(self, stale_setup: Setup) -> None:
        origin, ws, new_tip = stale_setup
        _add(ws, "--no-fetch")

        runner.invoke(app, ["rm", "-w", str(ws), "--dry-run", "--no-fetch"])

        assert _git(["rev-parse", "origin/main"], cwd=origin.canonical).strip() != new_tip

    @pytest.mark.parametrize("args", [["rm", "--dry-run"], ["drop", "api", "--dry-run"]])
    def test_an_unreachable_remote_only_warns(
        self, stale_setup: Setup, tmp_path: Path, args: list[str]
    ) -> None:
        """Like git, work offline: judge by the remote refs already there, and say so."""

        origin, ws, _ = stale_setup
        _add(ws)
        _git(["remote", "set-url", "origin", str(tmp_path / "gone.git")], cwd=origin.canonical)

        result = runner.invoke(app, [*args, "-w", str(ws)])

        assert result.exit_code == 0, result.output
        assert "warning:" in result.output
        assert "could not fetch 'origin'" in result.output
        assert "last fetch" in result.output
        assert (ws / "api").exists()

    @pytest.mark.parametrize("args", [["rm", "--dry-run"], ["drop", "api", "--dry-run"]])
    def test_the_warning_is_in_the_json_too(
        self, stale_setup: Setup, tmp_path: Path, args: list[str]
    ) -> None:
        origin, ws, _ = stale_setup
        _add(ws)
        _git(["remote", "set-url", "origin", str(tmp_path / "gone.git")], cwd=origin.canonical)

        result = runner.invoke(app, [*args, "-w", str(ws), "--json"])

        payload = json.loads(result.output)
        assert len(payload["fetch_warnings"]) == 1
        assert "could not fetch 'origin'" in payload["fetch_warnings"][0]

    def test_work_that_is_not_pushed_is_still_refused_while_offline(
        self, stale_setup: Setup, tmp_path: Path
    ) -> None:
        origin, ws, _ = stale_setup
        worktree = _add(ws)
        _commit(worktree, "my work")
        _git(["remote", "set-url", "origin", str(tmp_path / "gone.git")], cwd=origin.canonical)

        result = runner.invoke(app, ["rm", "-w", str(ws), "--dry-run"])

        assert result.exit_code != 0
        assert "refused:" in result.output
        assert "warning:" in result.output

    def test_one_failing_remote_does_not_stop_the_others_from_being_fetched(
        self, stale_setup: Setup, tmp_path: Path
    ) -> None:
        origin, ws, new_tip = stale_setup
        _add(ws, "--no-fetch")
        _git(["remote", "add", "dead", str(tmp_path / "gone.git")], cwd=origin.canonical)

        result = runner.invoke(app, ["rm", "-w", str(ws), "--dry-run"])

        assert "could not fetch 'dead'" in result.output
        assert _git(["rev-parse", "origin/main"], cwd=origin.canonical).strip() == new_tip

    @pytest.mark.parametrize("args", [["rm"], ["drop", "api"]])
    def test_offline_works_with_no_fetch(
        self, stale_setup: Setup, tmp_path: Path, args: list[str]
    ) -> None:
        origin, ws, _ = stale_setup
        _add(ws)
        _git(["remote", "set-url", "origin", str(tmp_path / "gone.git")], cwd=origin.canonical)

        result = runner.invoke(app, [*args, "-w", str(ws), "--no-fetch"])

        assert result.exit_code == 0, result.output
        assert not (ws / "api").exists()


def test_a_set_fetches_each_clone_once(
    stale_setup: Setup, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
) -> None:
    """Two member workspaces on one clone: one fetch, however many times the members are judged."""

    origin, _, _ = stale_setup
    set_root = isolated_home / "set"
    assert runner.invoke(app, ["init", "set", "--set", "-p", str(isolated_home)]).exit_code == 0
    for member in ("m1", "m2"):
        runner.invoke(app, ["init", member, "-p", str(set_root)])
        runner.invoke(app, ["add", "kybernetix/api", "-w", str(set_root / member)])
    calls: list[Path] = []
    real = git_remote.fetch_every_remote
    monkeypatch.setattr(
        git_remote, "fetch_every_remote", lambda path: (calls.append(path), real(path))[1]
    )

    result = runner.invoke(app, ["rm", "-w", str(set_root), "--dry-run"])

    assert result.exit_code == 0, result.output
    assert calls == [origin.canonical]


class TestRemoteThatPlainFetchAllSkips:
    """`remote.<name>.skipDefaultUpdate` makes `git fetch --all` skip a remote silently."""

    def test_a_branch_deleted_on_a_skipped_remote_is_still_pruned(self, stale_setup: Setup) -> None:
        origin, ws, _ = stale_setup
        worktree = _add(ws)
        _commit(worktree, "only ever pushed to a branch that is now gone")
        _git(["push", "-u", "origin", "task-1"], cwd=worktree)
        _git(["config", "remote.origin.skipDefaultUpdate", "true"], cwd=origin.canonical)
        _git(["branch", "-D", "task-1"], cwd=origin.bare)

        result = runner.invoke(app, ["rm", "-w", str(ws), "--dry-run"])

        assert result.exit_code != 0
        assert "1 unpushed commit" in result.output


def test_a_set_reports_a_failed_fetch_once_per_clone(
    stale_setup: Setup, isolated_home: Path, tmp_path: Path
) -> None:
    origin, _, _ = stale_setup
    set_root = isolated_home / "set"
    assert runner.invoke(app, ["init", "set", "--set", "-p", str(isolated_home)]).exit_code == 0
    for member in ("m1", "m2"):
        runner.invoke(app, ["init", member, "-p", str(set_root)])
        runner.invoke(app, ["add", "kybernetix/api", "-w", str(set_root / member)])
    _git(["remote", "set-url", "origin", str(tmp_path / "gone.git")], cwd=origin.canonical)

    result = runner.invoke(app, ["rm", "-w", str(set_root), "--dry-run", "--json"])

    assert result.exit_code == 0, result.output
    assert len(json.loads(result.output)["fetch_warnings"]) == 1
