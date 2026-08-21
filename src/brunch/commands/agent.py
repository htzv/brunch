"""Controllers for ``br agent`` — start, list, resume, register, and reconcile
coding-agent conversations scoped to a brunch workspace.

The heavy lifting (discovery, the registered/discovered/stale merge, capture)
lives in :mod:`brunch.services.agent`; these functions handle CLI wiring,
rendering, and the one thing a service can't: actually launching the agent
process and (for OpenCode) capturing the id it assigns.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import get_args

import typer
from rich.console import Console
from rich.markup import escape

from brunch import experimental
from brunch.errors import AgentError
from brunch.models import AgentConversation, AgentKind
from brunch.paths import discover_workspace
from brunch.rendering import render_agent_list, render_agent_rm, render_agent_sync
from brunch.services import agent as svc

_KINDS = get_args(AgentKind)  # ("claude", "opencode")


def _validate_kind(agent: str) -> AgentKind:
    if agent not in _KINDS:
        raise AgentError(
            f"unknown agent {agent!r}",
            hint=f"Supported agents: {', '.join(_KINDS)}.",
        )
    return agent  # type: ignore[return-value]


def _capture_in_background(location: object, plan: svc.NewPlan) -> None:
    """Poll the store briefly so a new OpenCode id is recorded within seconds.

    Best-effort and silent (never prints — the agent TUI owns the terminal).
    If it misses, the post-exit reconcile in ``agent_new`` or ``br agent sync``
    catches the session later.
    """

    def _poll() -> None:
        for _ in range(8):
            time.sleep(1.5)
            try:
                if svc.capture_new(location, plan):  # type: ignore[arg-type]
                    return
            except Exception:
                return

    threading.Thread(target=_poll, daemon=True).start()


def agent_new(
    agent: str = typer.Argument(..., help="Which agent to start: claude | opencode."),
    label: str | None = typer.Option(None, "--label", "-l", help="Friendly name for the session."),
    subdir: str | None = typer.Option(
        None, "-C", "--dir", help="Launch in this subdir of the workspace (worktree / nested)."
    ),
    workspace: Path | None = typer.Option(
        None, "-w", "--workspace", help="Operate on the workspace at this path (default: cwd)."
    ),
) -> None:
    """Start a new agent conversation and record it in brunch.toml."""

    kind = _validate_kind(agent)
    location = discover_workspace(workspace or Path.cwd())
    console = Console()

    plan = svc.plan_new(location, kind, label=label, subdir=subdir)

    if plan.session_id is not None:
        # Claude: id assigned up front, entry already recorded.
        console.print(
            f"[green]recorded[/green] {kind} {plan.handle[:8]} "
            f"[dim]{escape(f'[{plan.directory}]')}[/dim] — starting…"
        )
    else:
        # OpenCode: capture the id it assigns, in the background and again on exit.
        console.print(
            f"[cyan]starting[/cyan] {kind} "
            f"[dim]{escape(f'[{plan.directory}]')}[/dim] — will record on launch…"
        )
        _capture_in_background(location, plan)

    try:
        subprocess.run(plan.argv, cwd=str(plan.directory), check=False)
    except FileNotFoundError as e:
        raise AgentError(
            f"{plan.argv[0]!r} is not on PATH.", hint=f"Install {kind} or fix your PATH."
        ) from e

    recorded = svc.capture_new(location, plan)  # idempotent final reconcile
    if recorded:
        handles = ", ".join(e.handle[:8] for e in recorded)
        console.print(f"[green]recorded[/green] {kind} {handles}")
    elif plan.session_id is None:
        console.print(
            "[yellow]note[/yellow]: could not detect a new session id — "
            "run `br agent sync` if you started one."
        )


def agent_list(
    workspace: Path | None = typer.Option(
        None, "-w", "--workspace", help="Operate on the workspace at this path (default: cwd)."
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON instead of a table."),
) -> None:
    """List agent conversations for this workspace (recorded + discovered)."""

    location = discover_workspace(workspace or Path.cwd())
    listing = svc.list_conversations(location)
    if json_output:
        typer.echo(listing.model_dump_json(indent=2))
    else:
        render_agent_list(listing)


def _pick(conversations: list[AgentConversation], console: Console) -> AgentConversation:
    """Interactive numbered picker; errors if there's no tty to prompt on."""

    if not sys.stdin.isatty():
        raise AgentError(
            "multiple conversations match; a selector is required in non-interactive use.",
            hint="Pass a handle, label, or session-id prefix: `br agent resume <selector>`.",
        )
    for i, c in enumerate(conversations, 1):
        name = c.label or c.title or ""
        console.print(
            f"  [bold]{i}[/bold]. {c.agent}  [dim]{escape(f'[{c.dir}]')}[/dim]  {escape(name)}"
        )
    choice: int = typer.prompt("resume which? (number)", type=int)
    if not 1 <= choice <= len(conversations):
        raise AgentError(f"choice {choice} out of range (1-{len(conversations)}).")
    return conversations[choice - 1]


def agent_resume(
    selector: str | None = typer.Argument(
        None, help="Handle, label, or session-id (prefix ok). Omit to pick from a list."
    ),
    workspace: Path | None = typer.Option(
        None, "-w", "--workspace", help="Operate on the workspace at this path (default: cwd)."
    ),
) -> None:
    """Resume a recorded conversation (cd to its dir, then hand off to the agent)."""

    import os

    location = discover_workspace(workspace or Path.cwd())
    console = Console()
    listing = svc.list_conversations(location)
    if not listing.conversations:
        raise AgentError(
            "no agent conversations for this workspace.",
            hint="Start one with `br agent new <claude|opencode>`.",
        )

    if selector:
        conv = svc.match_conversation(listing.conversations, selector)
        if conv is None:
            raise AgentError(
                f"no conversation matches {selector!r} (or the prefix is ambiguous).",
                hint="Run `br agent list` to see handles.",
            )
    elif len(listing.conversations) == 1:
        conv = listing.conversations[0]
    else:
        conv = _pick(listing.conversations, console)

    argv, cwd = svc.resume_invocation(conv, location.root)
    name = conv.label or conv.title or conv.session
    console.print(
        f"[green]resuming[/green] {conv.agent} {escape(name)} [dim]{escape(f'[{cwd}]')}[/dim]"
    )
    # Hand the terminal to the agent, replacing brunch.
    os.chdir(cwd)
    try:
        os.execvp(argv[0], argv)
    except OSError as e:  # pragma: no cover — execvp only returns on failure
        raise AgentError(f"failed to exec {argv[0]!r}: {e}") from e


def agent_register(
    agent: str = typer.Argument(..., help="Which agent: claude | opencode."),
    session: str = typer.Argument(..., help="Native session id to record."),
    label: str | None = typer.Option(None, "--label", "-l", help="Friendly name."),
    subdir: str | None = typer.Option(
        None, "-C", "--dir", help="Launch dir relative to the workspace (default: auto-detect)."
    ),
    workspace: Path | None = typer.Option(
        None, "-w", "--workspace", help="Operate on the workspace at this path (default: cwd)."
    ),
) -> None:
    """Record a conversation you started outside `br agent new`."""

    kind = _validate_kind(agent)
    location = discover_workspace(workspace or Path.cwd())
    directory = (location.root / subdir) if subdir else None
    entry = svc.register(location, kind, session, label=label, directory=directory)
    label_suffix = f" {escape(entry.label)}" if entry.label else ""
    Console().print(
        f"[green]recorded[/green] {kind} {entry.handle[:8]} "
        f"[dim]{escape(f'[{entry.dir}]')}[/dim]{label_suffix}"
    )


def agent_sync(
    prune: bool = typer.Option(
        False, "--prune", help="Also drop recorded entries whose session is gone from the store."
    ),
    workspace: Path | None = typer.Option(
        None, "-w", "--workspace", help="Operate on the workspace at this path (default: cwd)."
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON instead of a summary."),
) -> None:
    """Reconcile brunch.toml against the agent stores (adopt discovered, flag/prune stale)."""

    location = discover_workspace(workspace or Path.cwd())
    report = svc.sync(location, prune=prune)
    if json_output:
        typer.echo(report.model_dump_json(indent=2))
    else:
        render_agent_sync(report)


def agent_rm(
    selector: str = typer.Argument(..., help="Handle, label, or session-id (prefix ok)."),
    purge: bool = typer.Option(
        False,
        "--purge",
        help="Also DELETE the underlying session from the agent's store (destructive).",
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Skip the 'looks active' guard when purging."
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the purge confirmation prompt."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would happen; change nothing."
    ),
    workspace: Path | None = typer.Option(
        None, "-w", "--workspace", help="Operate on the workspace at this path (default: cwd)."
    ),
) -> None:
    """Remove a conversation from the registry (and, with --purge, delete it)."""

    experimental.require("agent-rm")
    location = discover_workspace(workspace or Path.cwd())
    console = Console()

    # Confirm before an irreversible store deletion (preview via dry-run first,
    # which also runs the safety checks — so we refuse *before* prompting).
    if purge and not dry_run and not yes:
        preview = svc.remove(location, selector, purge=True, force=force, dry_run=True)
        if not preview.store_missing:
            target = escape(f"[{location.root / preview.dir}]")
            console.print(
                f"[red bold]Permanently delete[/red bold] the {preview.agent} session "
                f"{preview.session} from its store [dim]{target}[/dim]. "
                "[red]This cannot be undone.[/red]"
            )
            if not typer.confirm("Proceed?"):
                raise typer.Abort()

    outcome = svc.remove(location, selector, purge=purge, force=force, dry_run=dry_run)
    render_agent_rm(outcome)
