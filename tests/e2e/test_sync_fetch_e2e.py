"""`br sync` and `br init -t` create missing worktrees from the remote's current state."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from typer.testing import CliRunner

from brunch.cli import app
from tests.conftest import OriginRepo, _git

runner = CliRunner()
Setup = tuple[OriginRepo, Path, str]
BRANCH = "task-1"


def _declare_repo(ws: Path, branch: str = BRANCH, base: str = "main") -> None:
    """Add a [[repo]] entry to the manifest without creating its worktree."""

    manifest = ws / "brunch.toml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8")
        + f'\n[[repo]]\nrepo = "kybernetix/api"\nbranch = "{branch}"\nbase = "{base}"\n',
        encoding="utf-8",
    )


def _sync(ws: Path, *extra: str) -> tuple[int, str]:
    result = runner.invoke(app, ["sync", "-w", str(ws), *extra])
    return result.exit_code, result.output


def _config_get(repo: Path, key: str) -> str:
    result = subprocess.run(
        ["git", "config", "--get", key], cwd=repo, capture_output=True, text=True, check=False
    )
    return result.stdout.strip()


class TestSyncCreatesFromTheRemote:
    def test_a_new_branch_starts_at_the_remote_tip_without_tracking_it(
        self, stale_setup: Setup
    ) -> None:
        _, ws, new_tip = stale_setup
        _declare_repo(ws)

        code, output = _sync(ws)

        assert code == 0, output
        assert _git(["rev-parse", "HEAD"], cwd=ws / "api").strip() == new_tip
        assert _config_get(ws / "api", f"branch.{BRANCH}.remote") == ""
        assert "fetched 'origin'; starts from 'origin/main'" in " ".join(output.split())

    def test_a_branch_on_the_remote_is_taken_and_tracked(self, stale_setup: Setup) -> None:
        origin, ws, _ = stale_setup
        origin.publish_branch(BRANCH)
        tip = origin.advance(BRANCH)
        _declare_repo(ws)

        code, output = _sync(ws, "--json")

        assert code == 0, output
        action = json.loads(output)["actions"][0]
        assert action["tracks"] == f"origin/{BRANCH}"
        assert action["start_point"] == f"origin/{BRANCH}"
        assert _git(["rev-parse", "HEAD"], cwd=ws / "api").strip() == tip
        assert _config_get(ws / "api", f"branch.{BRANCH}.remote") == "origin"

    def test_json_reports_the_fetch(self, stale_setup: Setup) -> None:
        _, ws, _ = stale_setup
        _declare_repo(ws)

        _, output = _sync(ws, "--json")

        action = json.loads(output)["actions"][0]
        assert (action["remote"], action["start_point"], action["fetched"]) == (
            "origin",
            "origin/main",
            True,
        )

    def test_a_branch_that_exists_locally_is_checked_out_as_it_is_without_fetching(
        self, stale_setup: Setup, tmp_path: Path
    ) -> None:
        origin, ws, _ = stale_setup
        _git(["branch", BRANCH, "main"], cwd=origin.canonical)
        local_tip = _git(["rev-parse", BRANCH], cwd=origin.canonical).strip()
        _git(["remote", "set-url", "origin", str(tmp_path / "gone.git")], cwd=origin.canonical)
        _declare_repo(ws)

        code, output = _sync(ws)

        assert code == 0, output
        assert _git(["rev-parse", "HEAD"], cwd=ws / "api").strip() == local_tip
        assert "could not fetch" not in output

    def test_no_fetch_starts_from_the_local_base(self, stale_setup: Setup) -> None:
        origin, ws, new_tip = stale_setup
        local_main = _git(["rev-parse", "main"], cwd=origin.canonical).strip()
        assert local_main != new_tip
        _declare_repo(ws)

        code, output = _sync(ws, "--no-fetch")

        assert code == 0, output
        assert _git(["rev-parse", "HEAD"], cwd=ws / "api").strip() == local_main
        assert "not fetched (--no-fetch)" in " ".join(output.split())

    def test_dry_run_neither_fetches_nor_creates(self, stale_setup: Setup) -> None:
        origin, ws, new_tip = stale_setup
        _declare_repo(ws)

        code, output = _sync(ws, "--dry-run")

        assert code == 0, output
        assert not (ws / "api").exists()
        assert _git(["rev-parse", "origin/main"], cwd=origin.canonical).strip() != new_tip

    def test_remote_flag_picks_the_remote(self, stale_setup: Setup) -> None:
        origin, ws, new_tip = stale_setup
        _git(["remote", "rename", "origin", "company"], cwd=origin.canonical)
        _git(["remote", "add", "mirror", str(origin.bare)], cwd=origin.canonical)
        _declare_repo(ws)

        ambiguous_code, ambiguous = _sync(ws)
        named_code, named = _sync(ws, "-r", "company")

        assert ambiguous_code == 1
        assert "company, mirror" in ambiguous
        assert named_code == 0, named
        assert _git(["rev-parse", "HEAD"], cwd=ws / "api").strip() == new_tip


class TestFailuresAreReportedPerRepo:
    def test_an_unreachable_remote_is_an_error_for_that_repo_and_creates_nothing(
        self, stale_setup: Setup, tmp_path: Path
    ) -> None:
        origin, ws, _ = stale_setup
        _git(["remote", "set-url", "origin", str(tmp_path / "gone.git")], cwd=origin.canonical)
        _declare_repo(ws)

        code, output = _sync(ws)

        assert code == 1
        assert "could not fetch 'origin'" in output
        assert "--no-fetch" in output
        assert not (ws / "api").exists()

    def test_other_repos_are_still_created(
        self,
        stale_setup: Setup,
        tmp_path: Path,
        make_origin: Callable[..., OriginRepo],
    ) -> None:
        _, ws, _ = stale_setup
        second = make_origin("web")
        target = tmp_path / "canonical-root" / "github.com" / "kybernetix" / "web"
        shutil.move(str(second.canonical), str(target))
        _git(["remote", "set-url", "origin", str(tmp_path / "gone.git")], cwd=target)
        _declare_repo(ws)
        manifest = ws / "brunch.toml"
        manifest.write_text(
            manifest.read_text(encoding="utf-8")
            + f'\n[[repo]]\nrepo = "kybernetix/web"\nbranch = "{BRANCH}"\nbase = "main"\n',
            encoding="utf-8",
        )

        code, output = _sync(ws)

        assert code == 1
        assert (ws / "api" / ".git").exists()
        assert not (ws / "web").exists()
        assert "could not fetch" in output


class TestInitFromATemplate:
    def _template_home(self, home: Path) -> None:
        templates = home / ".config" / "brunch" / "templates"
        templates.mkdir(parents=True, exist_ok=True)
        (templates / "one.toml").write_text('[[repo]]\nrepo = "kybernetix/api"\n', encoding="utf-8")

    def test_worktrees_start_at_the_remote_tip(
        self, stale_setup: Setup, isolated_home: Path
    ) -> None:
        _, _, new_tip = stale_setup
        self._template_home(isolated_home)

        result = runner.invoke(app, ["init", "task-2", "-t", "one", "-p", str(isolated_home)])

        assert result.exit_code == 0, result.output
        assert _git(["rev-parse", "HEAD"], cwd=isolated_home / "task-2" / "api").strip() == new_tip

    def test_no_fetch_is_passed_on(self, stale_setup: Setup, isolated_home: Path) -> None:
        origin, _, new_tip = stale_setup
        self._template_home(isolated_home)

        result = runner.invoke(
            app, ["init", "task-2", "-t", "one", "-p", str(isolated_home), "--no-fetch"]
        )

        assert result.exit_code == 0, result.output
        head = _git(["rev-parse", "HEAD"], cwd=isolated_home / "task-2" / "api").strip()
        assert head == _git(["rev-parse", "main"], cwd=origin.canonical).strip() != new_tip
