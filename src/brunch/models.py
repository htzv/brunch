"""Pydantic models shared across modules.

Models that cross any boundary (CLI ↔ services, services ↔ persistence, --json
output) live here so the schema surface is consistent and machine-readable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# --- repo addressing -------------------------------------------------------


class RepoSpec(BaseModel):
    """A fully qualified repo reference (forge + org + name)."""

    model_config = ConfigDict(frozen=True)

    forge: str
    org: str
    name: str

    @property
    def short(self) -> str:
        """Short form, e.g. 'acme/api' (forge implied)."""
        return f"{self.org}/{self.name}"

    @property
    def qualified(self) -> str:
        """Fully qualified form, e.g. 'github.com/acme/api'."""
        return f"{self.forge}/{self.org}/{self.name}"


# --- manifests -------------------------------------------------------------


class RepoEntry(BaseModel):
    """A single [[repo]] entry in a workspace manifest."""

    model_config = ConfigDict(extra="forbid")

    repo: str = Field(description="Repo spec, e.g. 'acme/api' or 'github.com/acme/api'.")
    branch: str = Field(description="Branch to check out in the worktree.")
    base: str = Field(description="Branch this was started from / should be rebased onto.")


class WorkspaceManifest(BaseModel):
    """In-memory shape of a brunch.toml."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    name: str
    description: str | None = None
    repos: list[RepoEntry] = Field(default_factory=list, alias="repo")


class SetManifest(BaseModel):
    """In-memory shape of a brunch-set.toml."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None


# --- tool configuration ----------------------------------------------------


class ForgeConfig(BaseModel):
    """One forge entry in the tool config."""

    model_config = ConfigDict(extra="forbid")

    base_url: str


class ToolConfig(BaseModel):
    """In-memory shape of ~/.config/brunch/config.toml."""

    model_config = ConfigDict(extra="forbid")

    root: Path = Field(default=Path("~/repos/tw"))
    default_forge: str = Field(default="github.com")
    forges: dict[str, ForgeConfig] = Field(default_factory=dict)


# --- discovery -------------------------------------------------------------


WorkspaceMode = Literal["workspace", "set"]


class WorkspaceLocation(BaseModel):
    """Result of walk-up discovery."""

    model_config = ConfigDict(frozen=True)

    mode: WorkspaceMode
    root: Path
    manifest_path: Path


# --- git primitives --------------------------------------------------------


class GitStatus(BaseModel):
    """Raw status of a single git working tree (output of `git status v2`)."""

    branch: str | None = None  # None == detached HEAD
    ahead: int = 0
    behind: int = 0
    has_uncommitted: bool = False
    has_untracked: bool = False


class WorktreeRef(BaseModel):
    """One entry from `git worktree list --porcelain` on a canonical clone."""

    path: Path
    head: str | None = None
    branch: str | None = None  # short name, e.g. 'my-branch'; None if detached
    detached: bool = False


# --- status ----------------------------------------------------------------


class RepoStatus(BaseModel):
    """Status of one repo within a workspace."""

    repo_spec: str
    short_name: str
    worktree_path: Path
    exists: bool
    current_branch: str | None
    declared_branch: str
    declared_base: str
    on_declared_branch: bool
    ahead: int
    behind: int
    has_uncommitted: bool
    has_untracked: bool


class WorkspaceStatus(BaseModel):
    """Aggregate status of a whole workspace."""

    workspace_name: str
    workspace_path: Path
    description: str | None = None
    repos: list[RepoStatus]


# --- fsck ------------------------------------------------------------------


Severity = Literal["error", "warning", "info"]


class FsckFinding(BaseModel):
    """One issue surfaced by `brunch fsck`."""

    severity: Severity
    code: str
    message: str
    repo: str | None = None
    hint: str | None = None


class FsckReport(BaseModel):
    """Aggregate output of `brunch fsck`."""

    workspace_name: str
    workspace_path: Path
    findings: list[FsckFinding]

    @property
    def has_errors(self) -> bool:
        return any(f.severity == "error" for f in self.findings)

    @property
    def has_warnings(self) -> bool:
        return any(f.severity == "warning" for f in self.findings)


# --- sync / add / init -----------------------------------------------------


SyncActionType = Literal["created", "ok", "warning", "error"]


class SyncAction(BaseModel):
    """One per-repo outcome of a `brunch sync` pass."""

    repo: str
    short_name: str
    action: SyncActionType
    message: str
    hint: str | None = None


class SyncReport(BaseModel):
    """Aggregate outcome of `brunch sync`."""

    workspace_name: str
    workspace_path: Path
    actions: list[SyncAction]
    dry_run: bool = False

    @property
    def has_errors(self) -> bool:
        return any(a.action == "error" for a in self.actions)

    @property
    def has_warnings(self) -> bool:
        return any(a.action == "warning" for a in self.actions)


class AddOutcome(BaseModel):
    """Result of `brunch add`."""

    repo: str
    branch: str
    base: str
    worktree_path: Path
    dry_run: bool = False


class InitOutcome(BaseModel):
    """Result of `brunch init`."""

    name: str
    mode: WorkspaceMode
    path: Path
    template_id: str | None = None
    sync_report: SyncReport | None = None
    dry_run: bool = False
