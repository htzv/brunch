"""`br add` takes a branch that already exists on the remote, the way `git switch` does."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from brunch.cli import app
from tests.conftest import OriginRepo, _git

runner = CliRunner()
Setup = tuple[OriginRepo, Path, str]
PR_BRANCH = "pr-branch"


def _published_pr(origin: OriginRepo) -> str:
    """A branch on origin with two commits; returns its tip."""

    origin.publish_branch(PR_BRANCH)
    origin.advance(PR_BRANCH)
    return origin.advance(PR_BRANCH)


def _add(ws: Path, *extra: str) -> tuple[int, str]:
    result = runner.invoke(app, ["add", "kybernetix/api", "-w", str(ws), *extra])
    return result.exit_code, result.output


def _config_get(repo: Path, key: str) -> str:
    result = subprocess.run(
        ["git", "config", "--get", key], cwd=repo, capture_output=True, text=True, check=False
    )
    return result.stdout.strip()


class TestBranchExistsOnTheRemote:
    def test_the_branch_starts_at_the_remote_branch_and_tracks_it(self, stale_setup: Setup) -> None:
        origin, ws, _ = stale_setup
        tip = _published_pr(origin)

        code, output = _add(ws, "--branch", PR_BRANCH)

        assert code == 0, output
        worktree = ws / "api"
        assert _git(["rev-parse", "HEAD"], cwd=worktree).strip() == tip
        assert _config_get(worktree, f"branch.{PR_BRANCH}.remote") == "origin"
        assert _config_get(worktree, f"branch.{PR_BRANCH}.merge") == f"refs/heads/{PR_BRANCH}"
        assert "starts from 'origin/pr-branch' and tracks it" in " ".join(output.split())

    def test_git_then_knows_the_upstream(self, stale_setup: Setup) -> None:
        origin, ws, _ = stale_setup
        _published_pr(origin)
        _add(ws, "--branch", PR_BRANCH)
        origin.advance(PR_BRANCH)
        worktree = ws / "api"
        _git(["fetch", "origin"], cwd=worktree)

        status = _git(["status", "--porcelain=v2", "--branch"], cwd=worktree)

        assert f"# branch.upstream origin/{PR_BRANCH}" in status
        assert "# branch.ab +0 -1" in status

    def test_the_recorded_base_stays_the_default_branch(self, stale_setup: Setup) -> None:
        origin, ws, _ = stale_setup
        _published_pr(origin)

        _, output = _add(ws, "--branch", PR_BRANCH, "--json")

        payload = json.loads(output)
        assert payload["base"] == "main"
        assert payload["start_point"] == f"origin/{PR_BRANCH}"
        assert payload["tracks"] == f"origin/{PR_BRANCH}"

    def test_a_branch_not_on_the_remote_still_starts_from_the_base(
        self, stale_setup: Setup
    ) -> None:
        _, ws, new_tip = stale_setup

        _, output = _add(ws, "--json")

        payload = json.loads(output)
        assert payload["start_point"] == "origin/main"
        assert payload["tracks"] is None
        assert _git(["rev-parse", "HEAD"], cwd=ws / "api").strip() == new_tip

    def test_explicit_base_is_refused_and_nothing_is_created(self, stale_setup: Setup) -> None:
        origin, ws, _ = stale_setup
        _published_pr(origin)
        manifest_before = (ws / "brunch.toml").read_text(encoding="utf-8")

        code, output = _add(ws, "--branch", PR_BRANCH, "--base", "main")

        assert code == 10
        assert "'pr-branch' already exists on 'origin'" in output
        assert "--base 'main' would be ignored" in output
        assert "drop --base" in output
        assert not (ws / "api").exists()
        assert (ws / "brunch.toml").read_text(encoding="utf-8") == manifest_before

    def test_explicit_base_is_fine_when_the_branch_is_not_on_the_remote(
        self, stale_setup: Setup
    ) -> None:
        _, ws, _ = stale_setup
        code, output = _add(ws, "--base", "main")
        assert code == 0, output


class TestWhenTheRemoteIsNotAskedOrIsStale:
    def test_no_fetch_ignores_the_remote_branch(self, stale_setup: Setup) -> None:
        origin, ws, _ = stale_setup
        _published_pr(origin)
        _git(["fetch", "origin"], cwd=origin.canonical)
        local_main = _git(["rev-parse", "main"], cwd=origin.canonical).strip()

        code, output = _add(ws, "--branch", PR_BRANCH, "--no-fetch", "--base", "main")

        assert code == 0, output
        assert _git(["rev-parse", "HEAD"], cwd=ws / "api").strip() == local_main
        assert _config_get(ws / "api", f"branch.{PR_BRANCH}.remote") == ""

    def test_a_remote_branch_deleted_since_the_last_fetch_is_pruned_not_followed(
        self, stale_setup: Setup
    ) -> None:
        origin, ws, new_tip = stale_setup
        _published_pr(origin)
        _git(["fetch", "origin"], cwd=origin.canonical)
        _git(["branch", "-D", PR_BRANCH], cwd=origin.bare)

        code, output = _add(ws, "--branch", PR_BRANCH, "--json")

        assert code == 0, output
        payload = json.loads(output)
        assert payload["tracks"] is None
        assert payload["start_point"] == "origin/main"
        assert _git(["rev-parse", "HEAD"], cwd=ws / "api").strip() == new_tip

    def test_dry_run_reports_it_without_fetching_or_creating(self, stale_setup: Setup) -> None:
        origin, ws, _ = stale_setup
        _published_pr(origin)
        _git(["fetch", "origin"], cwd=origin.canonical)

        code, output = _add(ws, "--branch", PR_BRANCH, "--dry-run")

        assert code == 0, output
        assert "tracks it" in output
        assert not (ws / "api").exists()


class TestCleanupAfterTakingTheRemoteBranch:
    def test_rm_is_not_refused(self, stale_setup: Setup) -> None:
        origin, ws, _ = stale_setup
        _published_pr(origin)
        _add(ws, "--branch", PR_BRANCH)

        result = runner.invoke(app, ["rm", "-w", str(ws), "--dry-run"])

        assert result.exit_code == 0, result.output

    def test_a_commit_on_top_is_refused(self, stale_setup: Setup) -> None:
        origin, ws, _ = stale_setup
        _published_pr(origin)
        _add(ws, "--branch", PR_BRANCH)
        (ws / "api" / "review-fix.txt").write_text("fix\n", encoding="utf-8")
        _git(["add", "review-fix.txt"], cwd=ws / "api")
        _git(["commit", "-m", "review fix"], cwd=ws / "api")

        result = runner.invoke(app, ["rm", "-w", str(ws), "--dry-run"])

        assert result.exit_code != 0
        assert "1 unpushed commit" in result.output
