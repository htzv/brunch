"""Human-readable renderers for service results.

Kept separate from the controller code so the rendering pass is unit-testable
in isolation and easy to evolve without churning command modules.
"""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from brunch.models import FsckReport, RepoStatus, WorkspaceStatus

_SEVERITY_STYLE = {"error": "red", "warning": "yellow", "info": "cyan"}


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
