"""`br add` fetches the remote and starts new branches from its current tip."""

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
MakeOrigin = Callable[..., OriginRepo]


def _head(path: Path) -> str:
    return _git(["rev-parse", "HEAD"], cwd=path).strip()


def test_branch_starts_at_the_remote_tip_not_the_stale_local_main(
    stale_setup: tuple[OriginRepo, Path, str],
) -> None:
    origin, ws, new_tip = stale_setup
    stale_main = _git(["rev-parse", "main"], cwd=origin.canonical).strip()
    assert stale_main != new_tip

    result = runner.invoke(app, ["add", "kybernetix/api", "-w", str(ws)])

    assert result.exit_code == 0, result.output
    assert _head(ws / "api") == new_tip
    assert "fetched 'origin'; starts from 'origin/main'" in result.output
    assert _git(["rev-parse", "main"], cwd=origin.canonical).strip() == stale_main


def test_new_branch_does_not_track_main(stale_setup: tuple[OriginRepo, Path, str]) -> None:
    _, ws, _ = stale_setup
    runner.invoke(app, ["add", "kybernetix/api", "-w", str(ws)])
    tracking = subprocess.run(
        ["git", "config", "--get-regexp", r"^branch\.task-1\."],
        cwd=ws / "api",
        capture_output=True,
        text=True,
        check=False,
    )
    assert tracking.stdout == ""


def test_json_reports_remote_start_point_and_fetch(
    stale_setup: tuple[OriginRepo, Path, str],
) -> None:
    _, ws, _ = stale_setup
    result = runner.invoke(app, ["add", "kybernetix/api", "-w", str(ws), "--json"])
    payload = json.loads(result.output)
    assert payload["remote"] == "origin"
    assert payload["start_point"] == "origin/main"
    assert payload["fetched"] is True
    assert payload["base"] == "main"


def test_no_fetch_starts_from_the_local_base_and_says_so(
    stale_setup: tuple[OriginRepo, Path, str],
) -> None:
    origin, ws, new_tip = stale_setup
    stale_main = _git(["rev-parse", "main"], cwd=origin.canonical).strip()

    result = runner.invoke(app, ["add", "kybernetix/api", "-w", str(ws), "--no-fetch"])

    assert result.exit_code == 0, result.output
    assert _head(ws / "api") == stale_main != new_tip
    assert "not fetched (--no-fetch)" in result.output
    assert "local 'main'" in result.output


def test_unreachable_remote_fails_and_creates_nothing(
    stale_setup: tuple[OriginRepo, Path, str], tmp_path: Path
) -> None:
    origin, ws, _ = stale_setup
    _git(["remote", "set-url", "origin", str(tmp_path / "gone.git")], cwd=origin.canonical)
    manifest_before = (ws / "brunch.toml").read_text(encoding="utf-8")

    result = runner.invoke(app, ["add", "kybernetix/api", "-w", str(ws)])

    assert result.exit_code == 7
    assert "could not fetch 'origin'" in result.output
    assert "--no-fetch" in result.output
    assert not (ws / "api").exists()
    assert (ws / "brunch.toml").read_text(encoding="utf-8") == manifest_before


def test_dry_run_does_not_fetch(stale_setup: tuple[OriginRepo, Path, str]) -> None:
    origin, ws, new_tip = stale_setup
    result = runner.invoke(app, ["add", "kybernetix/api", "-w", str(ws), "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "would fetch 'origin'" in result.output
    assert not (ws / "api").exists()
    remote_tip = _git(["rev-parse", "origin/main"], cwd=origin.canonical).strip()
    assert remote_tip != new_tip


def test_two_remotes_without_origin_fail_until_one_is_named(
    stale_setup: tuple[OriginRepo, Path, str],
) -> None:
    origin, ws, new_tip = stale_setup
    _git(["remote", "rename", "origin", "company"], cwd=origin.canonical)
    _git(["remote", "add", "mirror", str(origin.bare)], cwd=origin.canonical)

    ambiguous = runner.invoke(app, ["add", "kybernetix/api", "-w", str(ws)])
    assert ambiguous.exit_code == 7
    assert "company, mirror" in ambiguous.output
    assert "--remote" in ambiguous.output
    assert not (ws / "api").exists()

    named = runner.invoke(app, ["add", "kybernetix/api", "-w", str(ws), "-r", "company"])
    assert named.exit_code == 0, named.output
    assert _head(ws / "api") == new_tip
    assert "fetched 'company'; starts from 'company/main'" in named.output


def test_repo_without_a_remote_skips_the_fetch_and_says_so(
    tmp_path: Path, isolated_home: Path, make_canonical: Callable[..., Path]
) -> None:
    root = tmp_path / "canonical-root"
    target = root / "github.com" / "kybernetix" / "api"
    target.parent.mkdir(parents=True)
    shutil.move(str(make_canonical("api")), str(target))
    config_dir = isolated_home / ".config" / "brunch"
    config_dir.mkdir(parents=True)
    (config_dir / "config.toml").write_text(f'root = "{root}"\n', encoding="utf-8")
    runner.invoke(app, ["init", "task-1", "-p", str(isolated_home)])

    result = runner.invoke(app, ["add", "kybernetix/api", "-w", str(isolated_home / "task-1")])

    assert result.exit_code == 0, result.output
    assert "no remote used" in result.output


def test_no_fetch_does_not_need_an_unambiguous_remote(
    stale_setup: tuple[OriginRepo, Path, str],
) -> None:
    """Without a fetch nothing depends on the remote, so several remotes are fine."""

    origin, ws, _ = stale_setup
    _git(["remote", "rename", "origin", "company"], cwd=origin.canonical)
    _git(["remote", "add", "mirror", str(origin.bare)], cwd=origin.canonical)

    result = runner.invoke(app, ["add", "kybernetix/api", "-w", str(ws), "--no-fetch"])

    assert result.exit_code == 0, result.output
    assert "no remote used" in result.output
    assert (ws / "api" / ".git").exists()


def test_no_fetch_still_rejects_a_remote_that_does_not_exist(
    stale_setup: tuple[OriginRepo, Path, str],
) -> None:
    _, ws, _ = stale_setup
    result = runner.invoke(
        app, ["add", "kybernetix/api", "-w", str(ws), "--no-fetch", "-r", "nope"]
    )
    assert result.exit_code == 7
    assert "no remote named 'nope'" in result.output


def test_branch_that_the_fetch_itself_creates_is_refused(
    stale_setup: tuple[OriginRepo, Path, str],
) -> None:
    """A mirror-style refspec turns the fetch into a way to create local branches."""

    origin, ws, _ = stale_setup
    origin.publish_branch("task-1")
    _git(["checkout", "-b", "scratch"], cwd=origin.canonical)
    _git(["config", "remote.origin.fetch", "+refs/heads/*:refs/heads/*"], cwd=origin.canonical)
    manifest_before = (ws / "brunch.toml").read_text(encoding="utf-8")

    result = runner.invoke(app, ["add", "kybernetix/api", "-w", str(ws)])

    assert result.exit_code == 10
    assert "'task-1' already exists" in result.output
    assert not (ws / "api").exists()
    assert (ws / "brunch.toml").read_text(encoding="utf-8") == manifest_before


class TestCleanupAfterAddingOnAStaleMain:
    """The commits a fetch brought in are not the user's work, but real work still counts."""

    def _added(self, stale_setup: tuple[OriginRepo, Path, str]) -> Path:
        _, ws, _ = stale_setup
        result = runner.invoke(app, ["add", "kybernetix/api", "-w", str(ws)])
        assert result.exit_code == 0, result.output
        return ws

    def test_rm_of_an_untouched_worktree_is_not_refused(
        self, stale_setup: tuple[OriginRepo, Path, str]
    ) -> None:
        ws = self._added(stale_setup)
        result = runner.invoke(app, ["rm", "-w", str(ws), "--dry-run"])
        assert result.exit_code == 0, result.output
        assert "refused" not in result.output

    def test_drop_of_an_untouched_worktree_is_not_refused(
        self, stale_setup: tuple[OriginRepo, Path, str]
    ) -> None:
        ws = self._added(stale_setup)
        result = runner.invoke(app, ["drop", "api", "-w", str(ws), "--dry-run"])
        assert result.exit_code == 0, result.output
        assert "refused" not in result.output

    def test_rm_still_refuses_a_real_unpublished_commit(
        self, stale_setup: tuple[OriginRepo, Path, str]
    ) -> None:
        ws = self._added(stale_setup)
        (ws / "api" / "mine.txt").write_text("my work\n", encoding="utf-8")
        _git(["add", "mine.txt"], cwd=ws / "api")
        _git(["commit", "-m", "my work"], cwd=ws / "api")
        result = runner.invoke(app, ["rm", "-w", str(ws), "--dry-run"])
        assert result.exit_code != 0
        assert "1 local-only commit" in result.output

    def test_drop_still_refuses_a_real_unpublished_commit(
        self, stale_setup: tuple[OriginRepo, Path, str]
    ) -> None:
        ws = self._added(stale_setup)
        (ws / "api" / "mine.txt").write_text("my work\n", encoding="utf-8")
        _git(["add", "mine.txt"], cwd=ws / "api")
        _git(["commit", "-m", "my work"], cwd=ws / "api")
        result = runner.invoke(app, ["drop", "api", "-w", str(ws), "--dry-run"])
        assert result.exit_code != 0
        assert "1 unpushed" in result.output
