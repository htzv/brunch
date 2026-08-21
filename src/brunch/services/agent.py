"""Service: register, discover, and resume coding-agent conversations.

Discovery-first hybrid (see docs/PRODUCT_PLAN.md § Pillar C):

  * The agent *stores* are the source of truth for what conversations exist —
    dir-scoped discovery finds them all, including forks and sessions started
    without the wrapper.
  * ``brunch.toml`` ``[[agent]]`` entries are an optional pin/label layer on
    top: a stable brunch handle, a friendly name, and intent.

``br agent list`` merges the two; ``sync`` reconciles them. The manifest holds
no store-derived fields (title, last-active) — those are read live so the
manifest never goes stale about them.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from brunch.agents import AgentProvider, all_providers, get_provider
from brunch.errors import AgentError
from brunch.manifest import load_workspace_manifest, write_workspace_manifest
from brunch.models import (
    AgentConversation,
    AgentEntry,
    AgentKind,
    AgentList,
    AgentRmOutcome,
    AgentSyncAction,
    AgentSyncReport,
    DiscoveredSession,
    WorkspaceLocation,
)

#: A session more recently active than this may be running right now; purging it
#: could pull the transcript out from under a live agent, so we guard on it.
_ACTIVE_WINDOW_S = 120


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _looks_active(last_active: str | None) -> bool:
    """True if the session was active within the last ``_ACTIVE_WINDOW_S`` seconds."""

    if not last_active:
        return False
    try:
        t = datetime.fromisoformat(last_active)
    except ValueError:
        return False
    now = datetime.now(t.tzinfo) if t.tzinfo else datetime.now(UTC)
    return (now - t).total_seconds() < _ACTIVE_WINDOW_S


def _reldir(directory: Path, root: Path) -> str:
    """``directory`` expressed relative to ``root`` as a POSIX string ('.' == root)."""

    try:
        rel = os.path.relpath(directory.resolve(), root.resolve())
    except ValueError:
        return "."
    return "." if rel == "" else Path(rel).as_posix()


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


# --- read side -------------------------------------------------------------


def list_conversations(
    location: WorkspaceLocation, *, providers: list[AgentProvider] | None = None
) -> AgentList:
    """Merge registered ``[[agent]]`` entries with live dir-scoped discovery."""

    manifest = load_workspace_manifest(location.manifest_path)
    provs = providers if providers is not None else all_providers()

    discovered: dict[tuple[AgentKind, str], DiscoveredSession] = {}
    for prov in provs:
        for d in prov.discover_under(location.root):
            discovered[(d.agent, d.session)] = d

    conversations: list[AgentConversation] = []
    seen: set[tuple[AgentKind, str]] = set()

    # Registered entries first, in manifest order (present → registered, else stale).
    for e in manifest.agents:
        key = (e.agent, e.session)
        seen.add(key)
        hit = discovered.get(key)
        conversations.append(
            AgentConversation(
                handle=e.handle,
                agent=e.agent,
                session=e.session,
                dir=e.dir,
                label=e.label,
                parent=e.parent,
                state="registered" if hit is not None else "stale",
                title=hit.title if hit else None,
                last_active=hit.last_active if hit else None,
            )
        )

    # Discovered-but-unregistered, most-recent first.
    extra = [
        AgentConversation(
            handle=None,
            agent=disc.agent,
            session=disc.session,
            dir=_reldir(disc.dir, location.root),
            state="discovered",
            title=disc.title,
            last_active=disc.last_active,
        )
        for key, disc in discovered.items()
        if key not in seen
    ]
    extra.sort(key=lambda c: c.last_active or "", reverse=True)

    return AgentList(
        workspace_name=manifest.name,
        workspace_path=location.root,
        conversations=conversations + extra,
    )


def match_conversation(
    conversations: list[AgentConversation], selector: str
) -> AgentConversation | None:
    """Resolve a user selector to one conversation, or ``None`` if absent/ambiguous.

    Order: exact handle/session, exact label (case-insensitive), then a unique
    prefix of handle or session. Ambiguous prefixes return ``None``.
    """

    for c in conversations:
        if c.handle == selector or c.session == selector:
            return c
    for c in conversations:
        if c.label and c.label.lower() == selector.lower():
            return c
    prefix = [
        c
        for c in conversations
        if (c.handle and c.handle.startswith(selector)) or c.session.startswith(selector)
    ]
    return prefix[0] if len(prefix) == 1 else None


def resume_invocation(conv: AgentConversation, root: Path) -> tuple[list[str], Path]:
    """argv + cwd to resume ``conv``. Raises if the agent CLI is missing."""

    prov = get_provider(conv.agent)
    if not prov.available():
        raise AgentError(
            f"{prov.cli!r} is not on PATH — cannot resume this {conv.agent} conversation.",
            hint=f"Install {conv.agent} or fix your PATH, then retry.",
        )
    cwd = (root / conv.dir).resolve()
    if not cwd.is_dir():
        raise AgentError(
            f"launch directory no longer exists: {cwd}",
            hint="The worktree/subdir was removed. `br agent sync --prune` to drop stale entries.",
        )
    return prov.resume_argv(conv.session), cwd


# --- write side ------------------------------------------------------------


def register(
    location: WorkspaceLocation,
    agent: AgentKind,
    session: str,
    *,
    handle: str | None = None,
    label: str | None = None,
    directory: Path | None = None,
    parent: str | None = None,
) -> AgentEntry:
    """Add (or return the existing) ``[[agent]]`` entry for ``(agent, session)``.

    Idempotent on ``(agent, session)``. When ``directory`` is omitted, the
    session's launch dir is recovered from the store if discoverable, else '.'.
    """

    manifest = load_workspace_manifest(location.manifest_path)
    for e in manifest.agents:
        if e.agent == agent and e.session == session:
            return e

    if directory is not None:
        reldir = _reldir(directory, location.root)
    else:
        reldir = "."
        for d in get_provider(agent).discover_under(location.root):
            if d.session == session:
                reldir = _reldir(d.dir, location.root)
                break

    entry = AgentEntry(
        handle=handle or str(uuid.uuid4()),
        agent=agent,
        session=session,
        dir=reldir,
        label=label,
        parent=parent,
        created=_now(),
    )
    manifest.agents.append(entry)
    write_workspace_manifest(location.manifest_path, manifest)
    return entry


def unregister(location: WorkspaceLocation, agent: AgentKind, session: str) -> bool:
    """Drop the ``[[agent]]`` entry for ``(agent, session)``. Returns True if removed."""

    manifest = load_workspace_manifest(location.manifest_path)
    before = len(manifest.agents)
    manifest.agents = [
        e for e in manifest.agents if not (e.agent == agent and e.session == session)
    ]
    if len(manifest.agents) == before:
        return False
    write_workspace_manifest(location.manifest_path, manifest)
    return True


# --- new (launch + capture) ------------------------------------------------


@dataclass
class NewPlan:
    """How to start a new conversation, and how to record it afterwards.

    ``session_id`` is set only when the agent accepts a caller-chosen id
    (Claude): the entry is registered up front and no capture is needed. For
    OpenCode, ``pre_snapshot`` holds the dir's session ids before launch; the
    new id is captured by diffing after the CLI starts.
    """

    agent: AgentKind
    directory: Path
    argv: list[str]
    handle: str
    label: str | None = None
    session_id: str | None = None
    pre_snapshot: set[str] = field(default_factory=set)


def plan_new(
    location: WorkspaceLocation,
    agent: AgentKind,
    *,
    label: str | None = None,
    subdir: str | None = None,
) -> NewPlan:
    """Prepare a new conversation. Registers up front iff the agent supports assigned ids."""

    prov = get_provider(agent)
    if not prov.available():
        raise AgentError(
            f"{prov.cli!r} is not on PATH.",
            hint=f"Install {agent} or fix your PATH.",
        )

    directory = (location.root / subdir).resolve() if subdir else location.root.resolve()
    if not _is_under(directory, location.root):
        raise AgentError(
            f"{subdir!r} is outside the workspace root.",
            hint="`br agent new` must launch at the workspace root or a subdirectory of it.",
        )
    if not directory.is_dir():
        raise AgentError(f"launch directory does not exist: {directory}")

    if prov.supports_assigned_id:
        sid = str(uuid.uuid4())
        register(location, agent, sid, handle=sid, label=label, directory=directory)
        return NewPlan(
            agent=agent,
            directory=directory,
            argv=prov.launch_argv(session_id=sid),
            handle=sid,
            label=label,
            session_id=sid,
        )

    return NewPlan(
        agent=agent,
        directory=directory,
        argv=prov.launch_argv(session_id=None),
        handle=str(uuid.uuid4()),
        label=label,
        session_id=None,
        pre_snapshot=prov.session_ids_in(directory),
    )


def capture_new(location: WorkspaceLocation, plan: NewPlan) -> list[AgentEntry]:
    """Record the session id(s) that appeared since ``plan`` was launched.

    Idempotent — safe to call from a background poll AND again after the CLI
    exits. Claude sessions are already registered (``session_id`` set), so this
    is a no-op for them. The first new id takes the plan's handle/label; any
    extras (forks created during the session) get fresh handles parented to it.
    """

    if plan.session_id is not None:
        return []

    prov = get_provider(plan.agent)
    new_ids = sorted(prov.session_ids_in(plan.directory) - plan.pre_snapshot)
    if not new_ids:
        return []

    # Only act on ids not already recorded, so repeated calls (background poll +
    # post-exit reconcile) are idempotent in return value, not just in effect.
    manifest = load_workspace_manifest(location.manifest_path)
    already = {e.session for e in manifest.agents if e.agent == plan.agent}
    primary_taken = plan.handle in {e.handle for e in manifest.agents}
    fresh = [s for s in new_ids if s not in already]

    entries: list[AgentEntry] = []
    for sid in fresh:
        if not primary_taken:
            # First new session claims the plan's handle/label.
            entries.append(
                register(
                    location,
                    plan.agent,
                    sid,
                    handle=plan.handle,
                    label=plan.label,
                    directory=plan.directory,
                )
            )
            primary_taken = True
        else:
            # Extra ids (forks created during the session) get fresh handles.
            entries.append(
                register(location, plan.agent, sid, directory=plan.directory, parent=plan.handle)
            )
    return entries


# --- sync ------------------------------------------------------------------


def sync(location: WorkspaceLocation, *, prune: bool = False) -> AgentSyncReport:
    """Reconcile the manifest against the stores: adopt discovered, flag/prune stale."""

    listing = list_conversations(location)
    actions: list[AgentSyncAction] = []

    for c in listing.conversations:
        if c.state == "discovered":
            entry = register(
                location,
                c.agent,
                c.session,
                label=c.title,
                directory=(location.root / c.dir),
            )
            actions.append(
                AgentSyncAction(
                    action="adopted",
                    agent=c.agent,
                    handle=entry.handle,
                    session=c.session,
                    dir=entry.dir,
                    label=entry.label,
                    message="found in store, added to brunch.toml",
                )
            )
        elif c.state == "stale":
            if prune:
                unregister(location, c.agent, c.session)
                actions.append(
                    AgentSyncAction(
                        action="pruned",
                        agent=c.agent,
                        handle=c.handle or "",
                        session=c.session,
                        dir=c.dir,
                        label=c.label,
                        message="not found in store, removed from brunch.toml",
                    )
                )
            else:
                actions.append(
                    AgentSyncAction(
                        action="stale",
                        agent=c.agent,
                        handle=c.handle or "",
                        session=c.session,
                        dir=c.dir,
                        label=c.label,
                        message="recorded but not found in store (use --prune to drop)",
                    )
                )

    return AgentSyncReport(
        workspace_name=listing.workspace_name,
        workspace_path=location.root,
        actions=actions,
        pruned=prune,
    )


# --- rm --------------------------------------------------------------------


def remove(
    location: WorkspaceLocation,
    selector: str,
    *,
    purge: bool = False,
    force: bool = False,
    dry_run: bool = False,
) -> AgentRmOutcome:
    """Remove a conversation from the registry and, with ``purge``, from the store.

    Safety contract:
      * refuses an absent or ambiguous selector;
      * without ``--purge``, only unregisters — and refuses if the target isn't
        recorded (nothing to do);
      * ``--purge`` deletes from the store only when the session is actually
        present there; a stale entry just gets dropped (``store_missing``);
      * refuses to purge a session that looks active (recent activity) unless
        ``force``;
      * ``dry_run`` runs every check but changes nothing.
    """

    listing = list_conversations(location)
    if not listing.conversations:
        raise AgentError(
            "no agent conversations for this workspace.",
            hint="Nothing to remove — see `br agent list`.",
        )
    conv = match_conversation(listing.conversations, selector)
    if conv is None:
        raise AgentError(
            f"no conversation matches {selector!r} (or the prefix is ambiguous).",
            hint="Run `br agent list` to see handles.",
        )

    in_manifest = conv.state in ("registered", "stale")
    in_store = conv.state in ("registered", "discovered")
    name = conv.label or conv.title

    if not purge:
        if not in_manifest:
            raise AgentError(
                f"{selector!r} is discovered but not recorded — nothing to unregister.",
                hint=(
                    "Use --purge to delete it from the store, or `br agent sync` to adopt it first."
                ),
            )
        if not dry_run:
            unregister(location, conv.agent, conv.session)
        return AgentRmOutcome(
            agent=conv.agent,
            session=conv.session,
            dir=conv.dir,
            handle=conv.handle,
            label=name,
            unregistered=not dry_run,
            dry_run=dry_run,
        )

    # --- purge path (destructive) ---
    if in_store and not force and _looks_active(conv.last_active):
        raise AgentError(
            f"{conv.agent} session {conv.session} looks active (last activity <2m ago) — "
            "it may be running right now.",
            hint="Close that session first, or pass --force to purge it anyway.",
        )
    prov = get_provider(conv.agent)
    if in_store and conv.agent == "opencode" and not prov.available():
        raise AgentError(
            "'opencode' is not on PATH — needed to delete an OpenCode session.",
            hint="Install/adjust PATH, or drop just the registry entry without --purge.",
        )

    if dry_run:
        return AgentRmOutcome(
            agent=conv.agent,
            session=conv.session,
            dir=conv.dir,
            handle=conv.handle,
            label=name,
            purge=True,
            store_missing=not in_store,
            dry_run=True,
        )

    purged = False
    if in_store:
        try:
            purged = prov.delete_session(conv.session, location.root / conv.dir)
        except AgentError:
            raise
        except (OSError, ValueError, RuntimeError) as e:
            raise AgentError(f"failed to delete {conv.agent} session {conv.session}: {e}") from e
    if in_manifest:
        unregister(location, conv.agent, conv.session)

    return AgentRmOutcome(
        agent=conv.agent,
        session=conv.session,
        dir=conv.dir,
        handle=conv.handle,
        label=name,
        purge=True,
        purged=purged,
        store_missing=not in_store,
        unregistered=in_manifest,
    )
