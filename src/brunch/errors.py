"""Custom exception hierarchy for brunch.

Every brunch-aware error carries an exit code and an optional fix hint, so
the top-level CLI wrapper can render a consistent message + exit cleanly.
"""

from __future__ import annotations


class BrunchError(Exception):
    """Base class for all brunch-aware errors.

    Carries an exit code so the CLI wrapper can map errors to stable shell
    exit codes, and an optional hint that suggests how to recover.
    """

    exit_code: int = 1

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint

    def __str__(self) -> str:
        return self.message


class WorkspaceNotFoundError(BrunchError):
    """No brunch.toml or brunch-set.toml found by walk-up discovery."""

    exit_code = 3


class ManifestError(BrunchError):
    """brunch.toml or brunch-set.toml fails to parse or validate."""

    exit_code = 4


class ConfigError(BrunchError):
    """~/.config/brunch/config.toml fails to parse or validate."""

    exit_code = 5


class RepoSpecError(BrunchError):
    """A repo spec string is malformed."""

    exit_code = 6


class GitError(BrunchError):
    """A git subprocess failed in a way brunch couldn't recover from."""

    exit_code = 7


class TemplateError(BrunchError):
    """A template file is missing, malformed, or otherwise unusable."""

    exit_code = 8


class TargetExistsError(BrunchError):
    """A directory we were asked to create already exists."""

    exit_code = 9


class BranchConflictError(BrunchError):
    """A branch is already checked out in another worktree of the same canonical."""

    exit_code = 10


class DuplicateRepoError(BrunchError):
    """A repo entry already exists in the manifest."""

    exit_code = 11
