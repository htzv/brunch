"""End-to-end tests for set-mode commands.

Each test sets up a workspace set with two member workspaces and
exercises a command from the set root, checking both the aggregate
behaviour and the JSON shape.
"""

from __future__ import annotations

import json
import shutil
import tarfile
from collections.abc import Callable
from pathlib import Path

from typer.testing import CliRunner

from brunch.cli import app

runner = CliRunner()


def _install_canonical(
    make_canonical: Callable[..., Path], canonical_root: Path, *, name: str
) -> Path:
    target = canonical_root / "github.com" / "kybernetix" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(make_canonical(name)), str(target))
    return target


def _write_config(home: Path, *, root: Path) -> None:
    cfg_dir = home / ".config" / "brunch"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.toml").write_text(f'root = "{root}"\n', encoding="utf-8")


def _setup_set(
    isolated_home: Path,
    canonical_root: Path,
    make_canonical: Callable[..., Path],
    *,
    set_name: str = "2026-Q2_billing",
    members: list[tuple[str, list[str]]] | None = None,
) -> Path:
    """Create a set with the given members.

    ``members`` is a list of (workspace_name, [repo_short_names]); each
    repo is installed as a canonical and added to the member workspace.
    """

    members = members or [("task-1", ["api"]), ("task-2", ["api"])]
    # Install all unique canonicals once.
    installed: set[str] = set()
    for _, repos in members:
        for r in repos:
            if r in installed:
                continue
            _install_canonical(make_canonical, canonical_root, name=r)
            installed.add(r)
    _write_config(isolated_home, root=canonical_root)

    # Create the set, then each member workspace inside it, then add repos.
    runner.invoke(app, ["init", set_name, "--set", "-p", str(isolated_home)])
    set_root = isolated_home / set_name
    for ws_name, repos in members:
        runner.invoke(app, ["init", ws_name, "-p", str(set_root)])
        ws = set_root / ws_name
        for r in repos:
            runner.invoke(app, ["add", f"kybernetix/{r}", "-w", str(ws)])
    return set_root


# ---------------------------------------------------------------------------
# status / fsck / fetch at the set root
# ---------------------------------------------------------------------------


class TestSetStatusAndFsck:
    def test_status_aggregates_all_members(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        set_root = _setup_set(isolated_home, canonical_root, make_canonical)
        result = runner.invoke(app, ["status", "-w", str(set_root), "--json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["set_name"] == "2026-Q2_billing"
        names = sorted(m["workspace_name"] for m in payload["members"])
        assert names == ["task-1", "task-2"]

    def test_status_text_shows_member_headers(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        set_root = _setup_set(isolated_home, canonical_root, make_canonical)
        result = runner.invoke(app, ["status", "-w", str(set_root)])
        assert result.exit_code == 0
        assert "task-1" in result.output
        assert "task-2" in result.output

    def test_fsck_passes_for_clean_set(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        set_root = _setup_set(isolated_home, canonical_root, make_canonical)
        result = runner.invoke(app, ["fsck", "-w", str(set_root)])
        assert result.exit_code == 0
        assert result.output.count("all checks passed") == 2  # one per member

    def test_fsck_propagates_member_errors(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        set_root = _setup_set(isolated_home, canonical_root, make_canonical)
        # Break one member: delete its worktree dir.
        shutil.rmtree(set_root / "task-1" / "api")
        result = runner.invoke(app, ["fsck", "-w", str(set_root)])
        assert result.exit_code == 1
        assert "worktree-missing" in result.output


class TestSetFetch:
    def test_fetch_dry_run_aggregates(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        set_root = _setup_set(isolated_home, canonical_root, make_canonical)
        result = runner.invoke(app, ["fetch", "-w", str(set_root), "--dry-run", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["dry_run"] is True
        assert len(payload["members"]) == 2


# ---------------------------------------------------------------------------
# foreach across the set
# ---------------------------------------------------------------------------


class TestSetForeach:
    def test_foreach_runs_in_every_repo_of_every_member(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        set_root = _setup_set(
            isolated_home,
            canonical_root,
            make_canonical,
            members=[
                ("task-1", ["api"]),
                ("task-2", ["api"]),
            ],
        )
        result = runner.invoke(app, ["foreach", "-w", str(set_root), "--json", "--", "true"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert sum(len(m["actions"]) for m in payload["members"]) == 2
        assert all(a["action"] == "ok" for m in payload["members"] for a in m["actions"])


# ---------------------------------------------------------------------------
# rebase across the set
# ---------------------------------------------------------------------------


class TestSetRebase:
    def test_rebase_up_to_date_in_all_members(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        set_root = _setup_set(isolated_home, canonical_root, make_canonical)
        result = runner.invoke(app, ["rebase", "-w", str(set_root), "--no-fetch", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        for member in payload["members"]:
            for action in member["actions"]:
                assert action["action"] == "up_to_date"


# ---------------------------------------------------------------------------
# rm across the set — the most consequential set-mode operation
# ---------------------------------------------------------------------------


class TestSetRm:
    def test_clean_set_fully_removes(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        set_root = _setup_set(isolated_home, canonical_root, make_canonical)
        result = runner.invoke(app, ["rm", "-w", str(set_root), "--json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["action"] == "removed"
        assert payload["archive_path"] is None
        assert not set_root.exists()

    def test_dry_run_changes_nothing(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        set_root = _setup_set(isolated_home, canonical_root, make_canonical)
        result = runner.invoke(app, ["rm", "-w", str(set_root), "--dry-run"])
        assert result.exit_code == 0
        assert set_root.is_dir()
        assert (set_root / "task-1" / "api" / ".git").exists()

    def test_refused_when_any_member_has_uncommitted(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        set_root = _setup_set(isolated_home, canonical_root, make_canonical)
        # Dirty just one member.
        (set_root / "task-1" / "api" / "README.md").write_text("dirty\n", encoding="utf-8")
        result = runner.invoke(app, ["rm", "-w", str(set_root), "--json"])
        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert payload["action"] == "refused"
        # The refusing member shows up in members with action=refused.
        refused = [m for m in payload["members"] if m["action"] == "refused"]
        assert {m["workspace_name"] for m in refused} == {"task-1"}

    def test_force_archives_whole_set_once_and_removes(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        set_root = _setup_set(isolated_home, canonical_root, make_canonical)
        (set_root / "task-1" / "api" / "stash.txt").write_text("dirty\n", encoding="utf-8")

        result = runner.invoke(app, ["rm", "-w", str(set_root), "--force", "--json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["action"] == "removed"
        # One set-level archive (not two per-member ones).
        archive_dir = isolated_home / ".local" / "share" / "brunch" / "archives"
        archives = list(archive_dir.glob("2026-Q2_billing-*.tar.gz"))
        assert len(archives) == 1
        # The archive contains both members.
        with tarfile.open(archives[0]) as tar:
            names = tar.getnames()
        assert any("task-1/brunch.toml" in n for n in names)
        assert any("task-2/brunch.toml" in n for n in names)
        assert not set_root.exists()

    def test_partial_when_set_root_has_extra_content(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        set_root = _setup_set(isolated_home, canonical_root, make_canonical)
        # Drop an unknown sibling at the set root.
        (set_root / "ad-hoc-notes.md").write_text("important\n", encoding="utf-8")

        result = runner.invoke(app, ["rm", "-w", str(set_root), "--json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["action"] == "partial"
        # Set marker should have been removed since members were removed cleanly,
        # but the set dir survives because of the sibling.
        assert set_root.is_dir()
        assert (set_root / "ad-hoc-notes.md").read_text() == "important\n"
        preserved_names = {Path(p).name for p in payload["preserved"]}
        assert "ad-hoc-notes.md" in preserved_names

    def test_partial_when_a_member_ends_up_partial(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        set_root = _setup_set(isolated_home, canonical_root, make_canonical)
        # Sibling content inside one member so it ends up partial.
        (set_root / "task-1" / "scratch.md").write_text("x\n", encoding="utf-8")

        result = runner.invoke(app, ["rm", "-w", str(set_root)])
        assert result.exit_code == 0, result.output
        # The set dir survives because task-1 stayed (partial); task-2 went away.
        assert (set_root / "task-1" / "scratch.md").is_file()
        assert not (set_root / "task-2").exists()
        assert set_root.is_dir()


# ---------------------------------------------------------------------------
# Workspace-only commands at a set root behave consistently
# ---------------------------------------------------------------------------


class TestWorkspaceOnlyCommandsAtSetRoot:
    def test_add_at_set_root_refuses_clearly(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        set_root = _setup_set(isolated_home, canonical_root, make_canonical)
        result = runner.invoke(app, ["add", "kybernetix/api", "-w", str(set_root)])
        assert result.exit_code != 0
        assert "set" in result.output.lower() or "workspace" in result.output.lower()

    def test_sync_at_set_root_refuses_clearly(
        self,
        tmp_path: Path,
        isolated_home: Path,
        make_canonical: Callable[..., Path],
    ) -> None:
        canonical_root = tmp_path / "canonical-root"
        set_root = _setup_set(isolated_home, canonical_root, make_canonical)
        result = runner.invoke(app, ["sync", "-w", str(set_root)])
        assert result.exit_code != 0
