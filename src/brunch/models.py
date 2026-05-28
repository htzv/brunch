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
        """Short form, e.g. 'kybernetix/api' (forge implied)."""
        return f"{self.org}/{self.name}"

    @property
    def qualified(self) -> str:
        """Fully qualified form, e.g. 'github.com/kybernetix/api'."""
        return f"{self.forge}/{self.org}/{self.name}"


# --- manifests -------------------------------------------------------------


class RepoEntry(BaseModel):
    """A single [[repo]] entry in a workspace manifest."""

    model_config = ConfigDict(extra="forbid")

    repo: str = Field(
        description="Repo spec, e.g. 'kybernetix/api' or 'github.com/kybernetix/api'."
    )
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

    root: Path = Field(default=Path("~/repos/brunch"))
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
    upstream: str | None = None  # None == no upstream configured
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


# --- fetch / pull / rebase / foreach (M3) ----------------------------------


FetchActionType = Literal["fetched", "would_fetch", "skipped", "error"]


class FetchAction(BaseModel):
    """Per-repo outcome of `brunch fetch`."""

    repo: str
    short_name: str
    action: FetchActionType
    message: str
    hint: str | None = None


class FetchReport(BaseModel):
    """Aggregate outcome of `brunch fetch`."""

    workspace_name: str
    workspace_path: Path
    actions: list[FetchAction]
    dry_run: bool = False

    @property
    def has_errors(self) -> bool:
        return any(a.action == "error" for a in self.actions)


PullActionType = Literal["pulled", "would_pull", "skipped", "error"]


class PullAction(BaseModel):
    """Per-repo outcome of `brunch pull`."""

    repo: str
    short_name: str
    action: PullActionType
    message: str
    hint: str | None = None


class PullReport(BaseModel):
    """Aggregate outcome of `brunch pull`."""

    workspace_name: str
    workspace_path: Path
    actions: list[PullAction]
    dry_run: bool = False

    @property
    def has_errors(self) -> bool:
        return any(a.action == "error" for a in self.actions)


RebaseActionType = Literal[
    "rebased",
    "up_to_date",
    "conflict",
    "skipped",
    "would_rebase",
    "error",
]


class RebaseAction(BaseModel):
    """Per-repo outcome of `brunch rebase`."""

    repo: str
    short_name: str
    action: RebaseActionType
    target: str  # what we rebased onto (e.g. "origin/main")
    message: str
    hint: str | None = None


class RebaseReport(BaseModel):
    """Aggregate outcome of `brunch rebase`."""

    workspace_name: str
    workspace_path: Path
    actions: list[RebaseAction]
    dry_run: bool = False

    @property
    def has_errors(self) -> bool:
        return any(a.action == "error" for a in self.actions)

    @property
    def has_conflicts(self) -> bool:
        return any(a.action == "conflict" for a in self.actions)


ForeachActionType = Literal["ok", "failed", "skipped", "would_run", "error"]


class ForeachAction(BaseModel):
    """Per-repo outcome of `brunch foreach`."""

    repo: str
    short_name: str
    action: ForeachActionType
    exit_code: int | None = None
    stdout: str | None = None
    stderr: str | None = None
    message: str | None = None


class ForeachReport(BaseModel):
    """Aggregate outcome of `brunch foreach`."""

    workspace_name: str
    workspace_path: Path
    command: list[str]
    actions: list[ForeachAction]
    dry_run: bool = False

    @property
    def has_errors(self) -> bool:
        return any(a.action in ("failed", "error") for a in self.actions)


# --- set-level aggregates (M5) --------------------------------------------


class SetStatus(BaseModel):
    set_name: str
    set_path: Path
    description: str | None = None
    members: list[WorkspaceStatus] = Field(default_factory=list)


class SetFsckReport(BaseModel):
    set_name: str
    set_path: Path
    members: list[FsckReport] = Field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(m.has_errors for m in self.members)

    @property
    def has_warnings(self) -> bool:
        return any(m.has_warnings for m in self.members)


class SetFetchReport(BaseModel):
    set_name: str
    set_path: Path
    members: list[FetchReport] = Field(default_factory=list)
    dry_run: bool = False

    @property
    def has_errors(self) -> bool:
        return any(m.has_errors for m in self.members)


class SetPullReport(BaseModel):
    set_name: str
    set_path: Path
    members: list[PullReport] = Field(default_factory=list)
    dry_run: bool = False

    @property
    def has_errors(self) -> bool:
        return any(m.has_errors for m in self.members)


class SetRebaseReport(BaseModel):
    set_name: str
    set_path: Path
    members: list[RebaseReport] = Field(default_factory=list)
    dry_run: bool = False

    @property
    def has_errors(self) -> bool:
        return any(m.has_errors for m in self.members)

    @property
    def has_conflicts(self) -> bool:
        return any(m.has_conflicts for m in self.members)


class SetForeachReport(BaseModel):
    set_name: str
    set_path: Path
    command: list[str]
    members: list[ForeachReport] = Field(default_factory=list)
    dry_run: bool = False

    @property
    def has_errors(self) -> bool:
        return any(m.has_errors for m in self.members)


SetRmActionType = Literal[
    "removed",
    "partial",
    "would_remove",
    "refused",
    "no_op",
    "error",
]


class SetRmOutcome(BaseModel):
    """Aggregate outcome of `brunch rm` at a set root."""

    set_name: str
    set_path: Path
    action: SetRmActionType
    members: list[RmOutcome] = Field(default_factory=list)
    preserved: list[Path] = Field(default_factory=list)
    archive_path: Path | None = None
    forced: bool = False
    dry_run: bool = False

    @property
    def has_risks(self) -> bool:
        return any(m.has_risks for m in self.members)


# --- adopt -----------------------------------------------------------------


class AdoptSkip(BaseModel):
    """A direct child of the adoption target that was not adopted (and why)."""

    path: Path
    reason: str


class AdoptError(BaseModel):
    """A direct child that looked like a worktree but couldn't be adopted."""

    path: Path
    message: str
    hint: str | None = None


AdoptActionType = Literal["adopted", "would_adopt", "failed"]


class AdoptOutcome(BaseModel):
    """Result of ``brunch adopt`` (or ``brunch init --adopt``)."""

    name: str
    path: Path
    action: AdoptActionType
    discovered: list[RepoEntry] = Field(default_factory=list)
    skipped: list[AdoptSkip] = Field(default_factory=list)
    errors: list[AdoptError] = Field(default_factory=list)
    sync_report: SyncReport | None = None
    fsck_report: FsckReport | None = None
    dry_run: bool = False


# --- rm (M4) ---------------------------------------------------------------


class RmRisk(BaseModel):
    """A per-repo reason a workspace shouldn't be removed without --force."""

    repo: str
    short_name: str
    has_uncommitted: bool = False
    has_untracked: bool = False
    unpushed_commits: int = 0
    no_upstream: bool = False

    @property
    def is_at_risk(self) -> bool:
        return (
            self.has_uncommitted
            or self.has_untracked
            or self.unpushed_commits > 0
            or self.no_upstream
        )


RmRepoActionType = Literal["removed", "skipped", "would_remove", "error"]


class RmRepoAction(BaseModel):
    """Per-repo outcome of the removal pass."""

    repo: str
    short_name: str
    action: RmRepoActionType
    message: str


RmActionType = Literal[
    "removed",
    "partial",
    "would_remove",
    "refused",
    "no_op",
    "error",
]


class RmOutcome(BaseModel):
    """Aggregate outcome of `brunch rm`.

    ``preserved`` lists direct children of the workspace root that were left
    intact because they were not declared in the manifest. When this list is
    non-empty the action is ``partial``: the workspace dir itself was not
    removed, and ``brunch.toml`` was left in place so a future ``sync`` /
    ``rm`` can re-engage.
    """

    workspace_name: str
    workspace_path: Path
    action: RmActionType
    risks: list[RmRisk] = Field(default_factory=list)
    repo_actions: list[RmRepoAction] = Field(default_factory=list)
    preserved: list[Path] = Field(default_factory=list)
    archive_path: Path | None = None
    forced: bool = False
    dry_run: bool = False

    @property
    def has_risks(self) -> bool:
        return any(r.is_at_risk for r in self.risks)
