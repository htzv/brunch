"""Human-readable renderers for service results.

Kept separate from the controller code so the rendering pass is unit-testable
in isolation and easy to evolve without churning command modules.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from brunch.models import (
    AddOutcome,
    AdoptOutcome,
    FetchReport,
    ForeachReport,
    FsckReport,
    InitOutcome,
    PullReport,
    RebaseReport,
    RepoStatus,
    RmOutcome,
    SetFetchReport,
    SetForeachReport,
    SetFsckReport,
    SetPullReport,
    SetRebaseReport,
    SetRmOutcome,
    SetStatus,
    SyncReport,
    WorkspaceStatus,
)

_SEVERITY_STYLE = {"error": "red", "warning": "yellow", "info": "cyan"}
_SYNC_ACTION_STYLE = {
    "created": "green",
    "ok": "dim",
    "warning": "yellow",
    "error": "red",
}
_FETCH_ACTION_STYLE = {
    "fetched": "green",
    "would_fetch": "cyan",
    "skipped": "dim",
    "error": "red",
}
_PULL_ACTION_STYLE = {
    "pulled": "green",
    "would_pull": "cyan",
    "skipped": "dim",
    "error": "red",
}
_REBASE_ACTION_STYLE = {
    "rebased": "green",
    "up_to_date": "dim",
    "would_rebase": "cyan",
    "skipped": "dim",
    "conflict": "red",
    "error": "red",
}
_FOREACH_ACTION_STYLE = {
    "ok": "green",
    "failed": "red",
    "skipped": "dim",
    "would_run": "cyan",
    "error": "red",
}
_RM_REPO_ACTION_STYLE = {
    "removed": "green",
    "skipped": "dim",
    "would_remove": "cyan",
    "error": "red",
}


def render_workspace_status(status: WorkspaceStatus, *, console: Console | None = None) -> None:
    """Render a :class:`WorkspaceStatus` as a Rich table to ``console`` (or stdout)."""

    console = console or Console()
    console.print(f"[bold]workspace[/bold]  {status.workspace_name}")
    console.print(f"[bold]path[/bold]       {status.workspace_path}")
    if status.description:
        console.print(f"[bold]about[/bold]      {status.description}")

    if not status.repos:
        console.print("\n[dim](no repos in manifest)[/dim]")
        return

    table = Table(show_header=True, header_style="bold", padding=(0, 1))
    table.add_column("repo")
    table.add_column("branch")
    table.add_column("state")
    table.add_column("ahead/behind", justify="right")

    for r in status.repos:
        table.add_row(*_status_row(r))
    console.print()
    console.print(table)


def _status_row(r: RepoStatus) -> tuple[str, str, str, str]:
    repo_col = r.short_name
    if not r.exists:
        return repo_col, f"[dim]{r.declared_branch}[/dim]", "[red]missing[/red]", "-"

    if r.current_branch is None:
        branch_col = "[magenta](detached)[/magenta]"
    elif r.on_declared_branch:
        branch_col = r.current_branch
    else:
        branch_col = f"[magenta]{r.current_branch}[/magenta] (declared {r.declared_branch})"

    state_bits: list[str] = []
    if r.has_uncommitted:
        state_bits.append("uncommitted")
    if r.has_untracked:
        state_bits.append("untracked")
    if not state_bits:
        state_col = "[green]clean[/green]"
    else:
        state_col = "[yellow]" + ", ".join(state_bits) + "[/yellow]"

    ab = f"+{r.ahead}/-{r.behind}" if (r.ahead or r.behind) else "-"
    return repo_col, branch_col, state_col, ab


def render_fsck_report(report: FsckReport, *, console: Console | None = None) -> None:
    """Render a :class:`FsckReport` to ``console`` (or stdout)."""

    console = console or Console()
    console.print(f"[bold]workspace[/bold]  {report.workspace_name}")
    console.print(f"[bold]path[/bold]       {report.workspace_path}")

    if not report.findings:
        console.print("\n[green]all checks passed[/green]")
        return

    errors = sum(1 for f in report.findings if f.severity == "error")
    warnings = sum(1 for f in report.findings if f.severity == "warning")
    console.print(
        f"\n[red]{errors} error{_s(errors)}[/red], "
        f"[yellow]{warnings} warning{_s(warnings)}[/yellow]:\n"
    )

    for f in report.findings:
        style = _SEVERITY_STYLE.get(f.severity, "white")
        label = f.severity.upper()
        repo = f"  [{f.repo}]" if f.repo else ""
        console.print(f"  [{style}]{label:<7}[/{style}] {f.code}{repo}")
        console.print(f"          {f.message}")
        if f.hint:
            console.print(f"          [dim]hint:[/dim] {f.hint}")


def _s(n: int) -> str:
    return "" if n == 1 else "s"


# --- set-level renderers ---------------------------------------------------


def _set_header(
    *,
    console: Console,
    title: str,
    name: str,
    path: Path,
    n_members: int,
    extra: str | None = None,
    dry_run: bool = False,
) -> None:
    prefix = "[dim](dry-run)[/dim] " if dry_run else ""
    console.print(f"{prefix}[bold]{title}[/bold]  {name}")
    console.print(f"        [bold]path[/bold]  {path}")
    console.print(f"        [bold]members[/bold]  {n_members}")
    if extra:
        console.print(f"        [bold]{extra}[/bold]")


def _render_member_separator(console: Console, member_name: str, member_path: Path) -> None:
    console.print(f"\n[bold cyan]── {member_name}[/bold cyan] [dim]({member_path})[/dim]")


def render_set_status(report: SetStatus, *, console: Console | None = None) -> None:
    console = console or Console()
    _set_header(
        console=console,
        title="set",
        name=report.set_name,
        path=report.set_path,
        n_members=len(report.members),
    )
    if report.description:
        console.print(f"        [bold]about[/bold]  {report.description}")
    if not report.members:
        console.print("\n[dim](no member workspaces)[/dim]")
        return
    for member in report.members:
        _render_member_separator(console, member.workspace_name, member.workspace_path)
        render_workspace_status(member, console=console)


def render_set_fsck_report(report: SetFsckReport, *, console: Console | None = None) -> None:
    console = console or Console()
    _set_header(
        console=console,
        title="set fsck",
        name=report.set_name,
        path=report.set_path,
        n_members=len(report.members),
    )
    if not report.members:
        console.print("\n[dim](no member workspaces)[/dim]")
        return
    for member in report.members:
        _render_member_separator(console, member.workspace_name, member.workspace_path)
        render_fsck_report(member, console=console)


def render_set_fetch_report(report: SetFetchReport, *, console: Console | None = None) -> None:
    console = console or Console()
    _set_header(
        console=console,
        title="set fetch",
        name=report.set_name,
        path=report.set_path,
        n_members=len(report.members),
        dry_run=report.dry_run,
    )
    for member in report.members:
        _render_member_separator(console, member.workspace_name, member.workspace_path)
        render_fetch_report(member, console=console)


def render_set_pull_report(report: SetPullReport, *, console: Console | None = None) -> None:
    console = console or Console()
    _set_header(
        console=console,
        title="set pull",
        name=report.set_name,
        path=report.set_path,
        n_members=len(report.members),
        dry_run=report.dry_run,
    )
    for member in report.members:
        _render_member_separator(console, member.workspace_name, member.workspace_path)
        render_pull_report(member, console=console)


def render_set_rebase_report(report: SetRebaseReport, *, console: Console | None = None) -> None:
    console = console or Console()
    _set_header(
        console=console,
        title="set rebase",
        name=report.set_name,
        path=report.set_path,
        n_members=len(report.members),
        dry_run=report.dry_run,
    )
    for member in report.members:
        _render_member_separator(console, member.workspace_name, member.workspace_path)
        render_rebase_report(member, console=console)


def render_set_foreach_report(report: SetForeachReport, *, console: Console | None = None) -> None:
    console = console or Console()
    _set_header(
        console=console,
        title="set foreach",
        name=report.set_name,
        path=report.set_path,
        n_members=len(report.members),
        extra=f"command  {report.command}",
        dry_run=report.dry_run,
    )
    for member in report.members:
        _render_member_separator(console, member.workspace_name, member.workspace_path)
        render_foreach_report(member, console=console)


def render_set_rm_outcome(outcome: SetRmOutcome, *, console: Console | None = None) -> None:
    console = console or Console()
    prefix = "[dim](dry-run)[/dim] " if outcome.dry_run else ""
    console.print(f"{prefix}[bold]set rm[/bold]  {outcome.set_name}")
    console.print(f"        [bold]path[/bold]  {outcome.set_path}")

    if outcome.action == "refused":
        console.print("\n[red]refused[/red]: one or more member workspaces would refuse:\n")
        for member in outcome.members:
            if member.action != "refused":
                continue
            console.print(
                f"  [yellow]{member.workspace_name}[/yellow]  [dim]({member.workspace_path})[/dim]"
            )
            for r in member.risks:
                bits: list[str] = []
                if r.has_uncommitted:
                    bits.append("uncommitted")
                if r.has_untracked:
                    bits.append("untracked")
                if r.unpushed_commits > 0 and not r.no_upstream:
                    bits.append(f"{r.unpushed_commits} unpushed commit(s)")
                if r.no_upstream:
                    bits.append(f"{r.unpushed_commits} local-only commit(s) (no upstream)")
                joined = ", ".join(bits) or "unknown"
                console.print(f"      {r.short_name}: {joined}")
        console.print(
            "\n[dim]hint:[/dim] clean up the listed worktrees, or pass "
            "[bold]--force[/bold] to archive the whole set first."
        )
        return

    for member in outcome.members:
        _render_member_separator(console, member.workspace_name, member.workspace_path)
        render_rm_outcome(member, console=console)

    if outcome.archive_path is not None:
        verb = "would archive" if outcome.dry_run else "[green]archived[/green]"
        console.print(f"\n  {verb} to {outcome.archive_path}")

    if outcome.preserved:
        count = len(outcome.preserved)
        noun = "item" if count == 1 else "items"
        verb = "would preserve" if outcome.dry_run else "preserved"
        console.print(
            f"\n  [yellow]{verb} {count} non-manifest {noun}[/yellow] at the "
            f"set root {outcome.set_path}:"
        )
        for p in outcome.preserved:
            console.print(f"    - {p.name}")

    if outcome.action == "removed":
        console.print(f"\n[green]removed set[/green] {outcome.set_path}")
    elif outcome.action == "would_remove":
        console.print(f"\n[dim]would remove set[/dim] {outcome.set_path}")
    elif outcome.action == "partial":
        console.print(f"\n[yellow]set dir preserved[/yellow] at {outcome.set_path}")
        console.print(
            "[dim]hint:[/dim] brunch only deletes what manifests declare; "
            "review the items above and `rm -rf <path>` manually if you "
            "really want everything gone."
        )


def render_sync_report(report: SyncReport, *, console: Console | None = None) -> None:
    """Render a :class:`SyncReport`."""

    console = console or Console()
    prefix = "[dim](dry-run)[/dim] " if report.dry_run else ""
    console.print(f"{prefix}[bold]sync[/bold]  {report.workspace_name}")
    console.print(f"      [bold]path[/bold]  {report.workspace_path}")

    if not report.actions:
        console.print("\n[dim](no repos in manifest)[/dim]")
        return

    console.print()
    for action in report.actions:
        style = _SYNC_ACTION_STYLE.get(action.action, "white")
        label = action.action.upper()
        console.print(
            f"  [{style}]{label:<8}[/{style}] {action.short_name}  [dim]({action.repo})[/dim]"
        )
        console.print(f"           {action.message}")
        if action.hint:
            console.print(f"           [dim]hint:[/dim] {action.hint}")


def render_add_outcome(outcome: AddOutcome, *, console: Console | None = None) -> None:
    """Render an :class:`AddOutcome`."""

    console = console or Console()
    prefix = "[dim](dry-run)[/dim] " if outcome.dry_run else ""
    verb = "would add" if outcome.dry_run else "[green]added[/green]"
    console.print(f"{prefix}{verb} {outcome.repo} on {outcome.branch!r} (base {outcome.base!r})")
    console.print(f"        at {outcome.worktree_path}")


def _render_action_list(
    *,
    console: Console,
    title: str,
    workspace_name: str,
    workspace_path: Path,
    dry_run: bool,
    actions: list[Any],
    style_map: dict[str, str],
) -> None:
    """Shared shape for fetch / pull / rebase / foreach renderers."""

    prefix = "[dim](dry-run)[/dim] " if dry_run else ""
    console.print(f"{prefix}[bold]{title}[/bold]  {workspace_name}")
    console.print(f"      [bold]path[/bold]   {workspace_path}")

    if not actions:
        console.print("\n[dim](no repos in manifest)[/dim]")
        return

    console.print()
    for a in actions:
        style = style_map.get(a.action, "white")
        label = a.action.upper().replace("_", " ")
        console.print(f"  [{style}]{label:<12}[/{style}] {a.short_name}  [dim]({a.repo})[/dim]")
        if getattr(a, "message", None):
            console.print(f"               {a.message}")
        if getattr(a, "hint", None):
            console.print(f"               [dim]hint:[/dim] {a.hint}")


def render_fetch_report(report: FetchReport, *, console: Console | None = None) -> None:
    """Render a :class:`FetchReport`."""

    console = console or Console()
    _render_action_list(
        console=console,
        title="fetch",
        workspace_name=report.workspace_name,
        workspace_path=report.workspace_path,
        dry_run=report.dry_run,
        actions=report.actions,
        style_map=_FETCH_ACTION_STYLE,
    )


def render_pull_report(report: PullReport, *, console: Console | None = None) -> None:
    """Render a :class:`PullReport`."""

    console = console or Console()
    _render_action_list(
        console=console,
        title="pull",
        workspace_name=report.workspace_name,
        workspace_path=report.workspace_path,
        dry_run=report.dry_run,
        actions=report.actions,
        style_map=_PULL_ACTION_STYLE,
    )


def render_rebase_report(report: RebaseReport, *, console: Console | None = None) -> None:
    """Render a :class:`RebaseReport`. Targets are added inline."""

    console = console or Console()
    prefix = "[dim](dry-run)[/dim] " if report.dry_run else ""
    console.print(f"{prefix}[bold]rebase[/bold]  {report.workspace_name}")
    console.print(f"        [bold]path[/bold]   {report.workspace_path}")

    if not report.actions:
        console.print("\n[dim](no repos in manifest)[/dim]")
        return

    console.print()
    for a in report.actions:
        style = _REBASE_ACTION_STYLE.get(a.action, "white")
        label = a.action.upper().replace("_", " ")
        console.print(
            f"  [{style}]{label:<13}[/{style}] {a.short_name}  "
            f"[dim]({a.repo})[/dim]  [dim]→ {a.target}[/dim]"
        )
        if a.message:
            console.print(f"                {a.message}")
        if a.hint:
            console.print(f"                [dim]hint:[/dim] {a.hint}")


def render_foreach_report(report: ForeachReport, *, console: Console | None = None) -> None:
    """Render a :class:`ForeachReport`. Captured stdout/stderr is included
    if present (i.e. --json mode); in live-streaming mode the actual output
    has already been printed to the terminal."""

    console = console or Console()
    prefix = "[dim](dry-run)[/dim] " if report.dry_run else ""
    console.print(f"{prefix}[bold]foreach[/bold]  {report.workspace_name}")
    console.print(f"         [bold]path[/bold]    {report.workspace_path}")
    console.print(f"         [bold]command[/bold] {report.command}")

    if not report.actions:
        console.print("\n[dim](no repos in manifest)[/dim]")
        return

    console.print()
    for a in report.actions:
        style = _FOREACH_ACTION_STYLE.get(a.action, "white")
        label = a.action.upper().replace("_", " ")
        suffix = f" (exit {a.exit_code})" if a.exit_code is not None else ""
        console.print(
            f"  [{style}]{label:<10}[/{style}] {a.short_name}  [dim]({a.repo})[/dim]{suffix}"
        )
        if a.message:
            console.print(f"             {a.message}")


def render_rm_outcome(outcome: RmOutcome, *, console: Console | None = None) -> None:
    """Render an :class:`RmOutcome`."""

    console = console or Console()
    prefix = "[dim](dry-run)[/dim] " if outcome.dry_run else ""
    console.print(f"{prefix}[bold]rm[/bold]  {outcome.workspace_name}")
    console.print(f"    [bold]path[/bold]  {outcome.workspace_path}")

    if outcome.action == "refused":
        console.print("\n[red]refused[/red]: workspace has at-risk repos:\n")
        for r in outcome.risks:
            bits: list[str] = []
            if r.has_uncommitted:
                bits.append("uncommitted changes")
            if r.has_untracked:
                bits.append("untracked files")
            if r.unpushed_commits > 0 and not r.no_upstream:
                bits.append(f"{r.unpushed_commits} unpushed commit(s)")
            if r.no_upstream:
                bits.append(f"{r.unpushed_commits} local-only commit(s) (no upstream)")
            joined = ", ".join(bits) or "unknown"
            console.print(f"  [yellow]{r.short_name}[/yellow]  [dim]({r.repo})[/dim]")
            console.print(f"           {joined}")
        console.print(
            "\n[dim]hint:[/dim] commit/push/clean the worktrees, or pass [bold]--force[/bold] "
            "to archive everything first."
        )
        return

    if outcome.repo_actions:
        console.print()
        for a in outcome.repo_actions:
            style = _RM_REPO_ACTION_STYLE.get(a.action, "white")
            label = a.action.upper().replace("_", " ")
            console.print(f"  [{style}]{label:<13}[/{style}] {a.short_name}  [dim]({a.repo})[/dim]")
            console.print(f"                {a.message}")

    if outcome.archive_path is not None:
        verb = "would archive" if outcome.dry_run else "[green]archived[/green]"
        console.print(f"\n  {verb} to {outcome.archive_path}")

    if outcome.preserved:
        count = len(outcome.preserved)
        noun = "item" if count == 1 else "items"
        verb = "would preserve" if outcome.dry_run else "preserved"
        console.print(
            f"\n  [yellow]{verb} {count} non-manifest {noun}[/yellow] in {outcome.workspace_path}:"
        )
        for p in outcome.preserved:
            console.print(f"    - {p.name}")

    if outcome.action == "removed":
        console.print(f"\n[green]removed workspace[/green] {outcome.workspace_path}")
    elif outcome.action == "would_remove":
        console.print(f"\n[dim]would remove workspace[/dim] {outcome.workspace_path}")
    elif outcome.action == "partial":
        console.print(f"\n[yellow]workspace dir preserved[/yellow] at {outcome.workspace_path}")
        console.print(
            "[dim]hint:[/dim] brunch only deletes what the manifest declares; "
            "review the items above and `rm -rf <path>` manually if you really "
            "want everything gone."
        )


def render_adopt_outcome(outcome: AdoptOutcome, *, console: Console | None = None) -> None:
    """Render an :class:`AdoptOutcome`."""

    console = console or Console()
    prefix = "[dim](dry-run)[/dim] " if outcome.dry_run else ""
    if outcome.action == "adopted":
        verb = "[green]adopted[/green]"
    elif outcome.action == "would_adopt":
        verb = "would adopt"
    else:
        verb = "[red]failed[/red]"

    console.print(f"{prefix}{verb} {outcome.name}")
    console.print(f"        at {outcome.path}")

    if outcome.discovered:
        table = Table(show_header=True, header_style="bold", padding=(0, 1))
        table.add_column("repo")
        table.add_column("branch")
        table.add_column("base")
        for entry in outcome.discovered:
            table.add_row(entry.repo, entry.branch, entry.base)
        console.print()
        console.print(table)

    if outcome.skipped:
        console.print("\n[dim]skipped:[/dim]")
        for s in outcome.skipped:
            console.print(f"  - {s.path.name}: {s.reason}")

    if outcome.errors:
        console.print(f"\n[red]{len(outcome.errors)} error(s) — nothing was written[/red]")
        for e in outcome.errors:
            console.print(f"  [red]{e.path.name}[/red]: {e.message}")
            if e.hint:
                console.print(f"      [dim]hint:[/dim] {e.hint}")

    if outcome.action == "would_adopt":
        console.print(
            "\n[dim]review the inferred values above; `base` is defaulted to "
            "'main' — edit brunch.toml after adoption if your worktrees were "
            "branched off something else.[/dim]"
        )
        return

    if outcome.action == "adopted":
        if outcome.sync_report is not None:
            console.print()
            render_sync_report(outcome.sync_report, console=console)
        if outcome.fsck_report is not None:
            console.print()
            render_fsck_report(outcome.fsck_report, console=console)
        console.print(
            "\n[dim]reminder:[/dim] `base` was defaulted to 'main' for every "
            "repo. Edit brunch.toml if your worktrees were branched off "
            "something else, and re-run `brunch fsck` to verify."
        )


def render_init_outcome(outcome: InitOutcome, *, console: Console | None = None) -> None:
    """Render an :class:`InitOutcome`."""

    console = console or Console()
    prefix = "[dim](dry-run)[/dim] " if outcome.dry_run else ""
    verb = "would create" if outcome.dry_run else "[green]created[/green]"
    kind = "workspace set" if outcome.mode == "set" else "workspace"
    template = f" from template {outcome.template_id!r}" if outcome.template_id else ""
    console.print(f"{prefix}{verb} {kind} {outcome.name}{template}")
    console.print(f"        at {outcome.path}")
    if outcome.sync_report is not None:
        console.print()
        render_sync_report(outcome.sync_report, console=console)
