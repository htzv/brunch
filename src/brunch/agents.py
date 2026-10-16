"""Provider seam for coding-agent conversation stores.

This is the *only* module that reads an agent's on-disk session store or knows
how to invoke its CLI. Each provider exposes the same neutral surface —
directory-scoped discovery, an exact-dir id snapshot (for capture), and argv
builders for launch/resume — so the service layer stays agent-agnostic.

Design constraints (see docs/PRODUCT_PLAN.md):
  * Never deep-parse agent-internal formats. Read only stable signals
    (session id, launch cwd, a title record, a timestamp) and degrade
    gracefully — a malformed session must never crash `br agent list`.
  * Discovery keys on the launch directory, the same invariant the board
    relies on: Claude via the sanitized-cwd project slug, OpenCode via the
    ``session.directory`` column. This is what lets discovery catch forks and
    sessions started without the wrapper, for free.
"""

from __future__ import annotations

import os
import re
import shutil
import sqlite3
import subprocess
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from pathlib import Path

from brunch.models import AgentKind, DiscoveredSession

#: A native session id we're willing to put in a file path or argv. Real Claude
#: (UUID) and OpenCode (``ses_…``) ids match this; anything with a slash, ``..``,
#: whitespace, or shell metacharacters is rejected before any destructive use.
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")


def _iso(ms_or_epoch: float, *, unit: str = "s") -> str:
    """UTC ISO-8601 timestamp from an epoch value (seconds or milliseconds)."""

    secs = ms_or_epoch / 1000 if unit == "ms" else ms_or_epoch
    return datetime.fromtimestamp(secs, tz=UTC).isoformat()


def _is_under(path: Path, root: Path) -> bool:
    """True if ``path`` is ``root`` itself or nested beneath it."""

    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


class AgentProvider(ABC):
    """Neutral interface over one coding-agent's session store + CLI."""

    kind: AgentKind
    cli: str
    #: Whether the CLI can be told to use a caller-chosen session id at launch.
    supports_assigned_id: bool = False

    def available(self) -> bool:
        """True if the agent CLI is on PATH (needed only for launch/resume)."""

        return shutil.which(self.cli) is not None

    @abstractmethod
    def discover_under(self, root: Path) -> list[DiscoveredSession]:
        """Sessions whose launch dir is ``root`` or nested beneath it."""

    @abstractmethod
    def session_ids_in(self, directory: Path) -> set[str]:
        """Native session ids launched in exactly ``directory`` (for capture diffs)."""

    @abstractmethod
    def launch_argv(self, *, session_id: str | None) -> list[str]:
        """argv to start a NEW session (caller sets cwd)."""

    @abstractmethod
    def resume_argv(self, session: str) -> list[str]:
        """argv to resume an existing session by native id (caller sets cwd)."""

    @abstractmethod
    def delete_session(self, session_id: str, directory: Path) -> bool:
        """Permanently delete a session from the store (DESTRUCTIVE).

        ``directory`` is the session's launch dir (Claude needs it to locate the
        transcript; OpenCode deletes by id). Return True if something was
        deleted, False if it was already absent. Raise on failure.
        """


# --- Claude Code -----------------------------------------------------------


def _claude_slug(path: Path) -> str:
    """Claude's project-dir slug: absolute path with non-alphanumerics → '-'."""

    return re.sub(r"[^a-zA-Z0-9]", "-", str(path))


def default_claude_projects_dir() -> Path:
    """``~/.claude/projects`` (or ``$CLAUDE_CONFIG_DIR/projects``)."""

    base = os.environ.get("CLAUDE_CONFIG_DIR")
    root = Path(base).expanduser() if base else Path.home() / ".claude"
    return root / "projects"


class ClaudeProvider(AgentProvider):
    kind: AgentKind = "claude"
    cli = "claude"
    supports_assigned_id = True

    def __init__(self, projects_dir: Path | None = None) -> None:
        self._projects_dir = projects_dir or default_claude_projects_dir()

    @staticmethod
    def _read_meta(jsonl: Path) -> tuple[str | None, str | None]:
        """Return ``(cwd, title)`` from a session file, tolerating any garbage.

        Substring-prefiltered so we only JSON-decode the handful of lines that
        can carry the fields we want — never the large assistant/tool lines.
        """

        import json

        cwd: str | None = None
        title: str | None = None
        try:
            with jsonl.open(encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if cwd is None and '"cwd"' in line:
                        try:
                            cwd = json.loads(line).get("cwd") or None
                        except (ValueError, AttributeError):
                            pass
                    if '"ai-title"' in line:
                        try:
                            obj = json.loads(line)
                            if obj.get("type") == "ai-title":
                                title = obj.get("aiTitle") or title
                        except (ValueError, AttributeError):
                            pass
        except OSError:
            return None, None
        return cwd, title

    def _candidate_dirs(self, root: Path) -> list[Path]:
        rootslug = _claude_slug(root)
        if not self._projects_dir.is_dir():
            return []
        out: list[Path] = []
        try:
            for entry in os.scandir(self._projects_dir):
                if not entry.is_dir(follow_symlinks=False):
                    continue
                # exact root, or a nested dir (slug of a subpath = rootslug + "-…")
                if entry.name == rootslug or entry.name.startswith(rootslug + "-"):
                    out.append(Path(entry.path))
        except OSError:
            return []
        return out

    def discover_under(self, root: Path) -> list[DiscoveredSession]:
        root = root.resolve()
        found: list[DiscoveredSession] = []
        for proj in self._candidate_dirs(root):
            try:
                files = list(proj.glob("*.jsonl"))
            except OSError:
                continue
            for f in files:
                cwd, title = self._read_meta(f)
                # The slug is lossy; confirm against the recorded cwd when present.
                session_dir = Path(cwd) if cwd else root
                if cwd and not _is_under(session_dir, root):
                    continue
                try:
                    last = _iso(f.stat().st_mtime)
                except OSError:
                    last = None
                found.append(
                    DiscoveredSession(
                        agent="claude",
                        session=f.stem,
                        dir=session_dir,
                        title=title,
                        last_active=last,
                    )
                )
        return found

    def session_ids_in(self, directory: Path) -> set[str]:
        proj = self._projects_dir / _claude_slug(directory.resolve())
        if not proj.is_dir():
            return set()
        try:
            return {f.stem for f in proj.glob("*.jsonl")}
        except OSError:
            return set()

    def launch_argv(self, *, session_id: str | None) -> list[str]:
        if session_id:
            return [self.cli, "--session-id", session_id]
        return [self.cli]

    def resume_argv(self, session: str) -> list[str]:
        return [self.cli, "--resume", session]

    def delete_session(self, session_id: str, directory: Path) -> bool:
        # Claude has no delete CLI, so we remove the transcript file directly —
        # heavily guarded, since we're reaching into CC's internal storage.
        if not _SAFE_ID.match(session_id):
            raise ValueError(f"unsafe session id: {session_id!r}")
        projects_root = self._projects_dir.resolve()
        proj = (self._projects_dir / _claude_slug(directory.resolve())).resolve()
        target = (proj / f"{session_id}.jsonl").resolve()
        # The file must sit exactly one level under the projects root, in the
        # slug dir for this launch directory, and be named "<id>.jsonl" — never
        # anywhere a crafted id/dir could redirect us.
        if proj.parent != projects_root or target.parent != proj:
            raise ValueError(f"refusing to delete outside the projects dir: {target}")
        if target.name != f"{session_id}.jsonl":
            raise ValueError(f"unexpected delete target: {target.name}")
        if not target.exists():
            return False
        target.unlink()
        return True


# --- OpenCode --------------------------------------------------------------


def default_opencode_db_path() -> Path:
    """``~/.local/share/opencode/opencode.db`` (XDG data dir)."""

    base = os.environ.get("XDG_DATA_HOME")
    root = Path(base).expanduser() if base else Path.home() / ".local" / "share"
    return root / "opencode" / "opencode.db"


OPENCODE_SESSION_TABLES = ("session_v2", "session")
"""Newest first. OpenCode 2 writes new sessions to ``session_v2``; the older
``session`` table keeps the earlier ones, all of which ``session_v2`` also holds."""


def _opencode_sessions_table(conn: sqlite3.Connection) -> str | None:
    """The table holding OpenCode's sessions in this database, or None."""

    present = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    return next((t for t in OPENCODE_SESSION_TABLES if t in present), None)


class OpenCodeProvider(AgentProvider):
    kind: AgentKind = "opencode"
    cli = "opencode"
    supports_assigned_id = False  # no id-at-creation flag upstream (see PRODUCT_PLAN)

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or default_opencode_db_path()

    def _connect(self) -> sqlite3.Connection | None:
        if not self._db_path.is_file():
            return None
        try:
            return sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True, timeout=2.0)
        except sqlite3.Error:
            return None

    def discover_under(self, root: Path) -> list[DiscoveredSession]:
        root = root.resolve()
        conn = self._connect()
        if conn is None:
            return []
        out: list[DiscoveredSession] = []
        try:
            table = _opencode_sessions_table(conn)
            if table is None:
                return []
            rows = conn.execute(
                f"SELECT id, directory, title, time_updated FROM {table} "
                "WHERE parent_id IS NULL AND time_archived IS NULL "
                "AND (directory = ? OR directory LIKE ?) "
                "ORDER BY time_updated DESC",
                (str(root), f"{root}/%"),
            ).fetchall()
        except sqlite3.Error:
            return []
        finally:
            conn.close()
        for sid, directory, title, updated in rows:
            out.append(
                DiscoveredSession(
                    agent="opencode",
                    session=sid,
                    dir=Path(directory),
                    title=title or None,
                    last_active=_iso(updated, unit="ms") if updated else None,
                )
            )
        return out

    def session_ids_in(self, directory: Path) -> set[str]:
        conn = self._connect()
        if conn is None:
            return set()
        try:
            table = _opencode_sessions_table(conn)
            if table is None:
                return set()
            rows = conn.execute(
                f"SELECT id FROM {table} WHERE parent_id IS NULL AND directory = ?",
                (str(directory.resolve()),),
            ).fetchall()
        except sqlite3.Error:
            return set()
        finally:
            conn.close()
        return {r[0] for r in rows}

    def launch_argv(self, *, session_id: str | None) -> list[str]:
        # OpenCode can't be told a session id at creation; the new id is
        # captured post-launch by diffing session_ids_in().
        return [self.cli]

    def resume_argv(self, session: str) -> list[str]:
        return [self.cli, "--session", session]

    def delete_session(self, session_id: str, directory: Path) -> bool:
        # OpenCode has a stable delete CLI — prefer it over touching the DB, so
        # we don't depend on the (versioned) schema for a destructive write.
        del directory  # deletion is by id; the launch dir is irrelevant here
        if not _SAFE_ID.match(session_id):
            raise ValueError(f"unsafe session id: {session_id!r}")
        if not self.available():
            raise RuntimeError(f"{self.cli!r} not on PATH — cannot delete an OpenCode session")
        proc = subprocess.run(
            [self.cli, "session", "delete", session_id],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()[:200]
            raise RuntimeError(
                f"`opencode session delete` failed (exit {proc.returncode}): {detail}"
            )
        return True


# --- registry --------------------------------------------------------------


def get_provider(kind: AgentKind) -> AgentProvider:
    if kind == "claude":
        return ClaudeProvider()
    if kind == "opencode":
        return OpenCodeProvider()
    raise ValueError(f"unknown agent kind: {kind!r}")


def all_providers() -> list[AgentProvider]:
    return [ClaudeProvider(), OpenCodeProvider()]
