"""Typed wrappers around ``git`` subprocess calls.

Every function returns a structured result. Callers never see raw stdout.
Failures bubble up as ``GitError``s carrying both the command line and the
captured stderr, so error messages stay actionable.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from brunch.errors import GitError
from brunch.models import GitStatus, WorktreeRef


def _run(
    args: list[str], *, cwd: Path | None = None, check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Run a git command and return the CompletedProcess.

    Always captures stdout/stderr as text. With ``check=True`` (the default),
    a non-zero exit code raises ``GitError`` with full context.
    """

    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd) if cwd is not None else None,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as e:
        raise GitError(
            "git executable not found on PATH",
            hint="Install git or ensure it is reachable.",
        ) from e

    if check and result.returncode != 0:
        cmd = "git " + " ".join(args)
        raise GitError(
            f"`{cmd}` failed (exit {result.returncode}): {result.stderr.strip()}",
        )
    return result


def is_git_repo(path: Path) -> bool:
    """True if ``path`` is the working tree (or git dir) of a git repository."""

    if not path.exists():
        return False
    result = _run(["rev-parse", "--git-dir"], cwd=path, check=False)
    return result.returncode == 0


def current_branch(path: Path) -> str | None:
    """The short branch name at ``HEAD``, or ``None`` if detached."""

    return get_status(path).branch


def get_status(path: Path) -> GitStatus:
    """Parse ``git status --porcelain=v2 --branch`` into a ``GitStatus``."""

    result = _run(["status", "--porcelain=v2", "--branch"], cwd=path)
    return _parse_porcelain_v2(result.stdout)


def _parse_porcelain_v2(text: str) -> GitStatus:
    status = GitStatus()
    for line in text.splitlines():
        if not line:
            continue
        if line.startswith("# branch.head "):
            head = line.removeprefix("# branch.head ").strip()
            # Detached HEAD is rendered as "(detached)".
            status.branch = None if head == "(detached)" else head
        elif line.startswith("# branch.ab "):
            # `# branch.ab +<ahead> -<behind>`
            parts = line.removeprefix("# branch.ab ").split()
            for token in parts:
                if token.startswith("+"):
                    status.ahead = int(token[1:])
                elif token.startswith("-"):
                    status.behind = int(token[1:])
        elif line.startswith("?"):
            status.has_untracked = True
        elif line.startswith(("1 ", "2 ", "u ")):
            status.has_uncommitted = True
    return status


def worktree_list(canonical: Path) -> list[WorktreeRef]:
    """Parse ``git worktree list --porcelain`` against a canonical clone."""

    result = _run(["worktree", "list", "--porcelain"], cwd=canonical)
    return _parse_worktree_list(result.stdout)


def branch_exists(canonical: Path, branch: str) -> bool:
    """True if a local branch named ``branch`` exists in ``canonical``."""

    result = _run(
        ["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
        cwd=canonical,
        check=False,
    )
    return result.returncode == 0


def add_worktree(canonical: Path, target: Path, *, branch: str, base: str = "main") -> None:
    """Run ``git worktree add`` to materialise a worktree at ``target``.

    If ``branch`` already exists in ``canonical``, it is checked out as-is.
    Otherwise, it is created from ``base``. Either way, ``target`` ends up on
    ``branch``.
    """

    target.parent.mkdir(parents=True, exist_ok=True)
    if branch_exists(canonical, branch):
        _run(["worktree", "add", str(target), branch], cwd=canonical)
    else:
        _run(["worktree", "add", "-b", branch, str(target), base], cwd=canonical)


def remove_worktree(canonical: Path, target: Path, *, force: bool = False) -> None:
    """Run ``git worktree remove`` against ``target``.

    With ``force=True`` the worktree is removed even if it has local changes;
    callers are expected to confirm intent first.
    """

    args = ["worktree", "remove"]
    if force:
        args.append("--force")
    args.append(str(target))
    _run(args, cwd=canonical)


def rev_parse_verify(path: Path, ref: str) -> bool:
    """True if ``ref`` resolves to a commit in the repo at ``path``."""

    result = _run(["rev-parse", "--verify", "--quiet", ref], cwd=path, check=False)
    return result.returncode == 0


def has_remote(path: Path) -> bool:
    """True if the repo at ``path`` has any remote configured."""

    result = _run(["remote"], cwd=path, check=False)
    if result.returncode != 0:
        return False
    return bool(result.stdout.strip())


def fetch(path: Path) -> None:
    """Run ``git fetch`` (default remote) inside the worktree at ``path``.

    Raises ``GitError`` on any failure. Caller is responsible for handling
    "no remote configured" if it wants to degrade gracefully.
    """

    _run(["fetch"], cwd=path)


def pull(path: Path) -> None:
    """Run ``git pull`` (default remote, default merge strategy)."""

    _run(["pull"], cwd=path)


def rebase(
    path: Path,
    target: str,
    *,
    upstream: str | None = None,
    autostash: bool = False,
) -> None:
    """Run ``git rebase`` inside ``path``.

    When ``upstream`` is provided, the three-arg form is used:
    ``git rebase --onto <target> <upstream>``. Otherwise: ``git rebase
    <target>``.
    """

    args = ["rebase"]
    if autostash:
        args.append("--autostash")
    if upstream is not None:
        args.extend(["--onto", target, upstream])
    else:
        args.append(target)
    _run(args, cwd=path)


def rebase_in_progress(path: Path) -> bool:
    """True if a rebase is currently in progress (e.g. left after a conflict)."""

    result = _run(["rev-parse", "--git-dir"], cwd=path, check=False)
    if result.returncode != 0:
        return False
    git_dir = Path(result.stdout.strip())
    if not git_dir.is_absolute():
        git_dir = path / git_dir
    return (git_dir / "rebase-apply").exists() or (git_dir / "rebase-merge").exists()


def _parse_worktree_list(text: str) -> list[WorktreeRef]:
    refs: list[WorktreeRef] = []
    current: dict[str, str] = {}

    def flush() -> None:
        if not current:
            return
        refs.append(
            WorktreeRef(
                path=Path(current["worktree"]),
                head=current.get("HEAD"),
                branch=current.get("branch"),
                detached="detached" in current,
            )
        )
        current.clear()

    for line in text.splitlines():
        if not line.strip():
            flush()
            continue
        if line.startswith("worktree "):
            flush()
            current["worktree"] = line.removeprefix("worktree ").strip()
        elif line.startswith("HEAD "):
            current["HEAD"] = line.removeprefix("HEAD ").strip()
        elif line.startswith("branch "):
            full = line.removeprefix("branch ").strip()
            # 'refs/heads/<name>' → '<name>'
            current["branch"] = full.removeprefix("refs/heads/")
        elif line.strip() == "detached":
            current["detached"] = "true"
        # other lines (locked, prunable) are ignored for M1
    flush()
    return refs
