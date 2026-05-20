# brunch

Mise en place for git worktree-based multi-repo task workspaces.

A small CLI for setting up, synchronising, and tearing down **task workspaces** — directories of co-located git worktrees, one per repo, operated on as a unit. A worktree-aware spiritual successor to [myrepos (`mr`)](https://myrepos.branchable.com/), shaped around an agentic-coding workflow.

> **Status: M0 (skeleton).** The CLI surface is in place; most commands print a "not implemented" notice and exit non-zero. See [`docs/initial-design.md`](docs/initial-design.md) for the full functional design and the milestone roadmap.

## Quick links

- **[Walkthrough (MkDocs site)](docs-site/walkthrough/index.md)** — nine pages, one short asciinema cast each, taking a complete task end to end (create → Claude Code → test → commit → push → PR → teardown). Build locally with `uv sync --extra docs && uv run mkdocs serve`.
- [Getting started](docs/getting-started.md) — a guided tour from install to first workspace and back.
- [Functional design](docs/initial-design.md) — what brunch is, why each decision was made, alternatives considered, deferred work.
- [Example templates](docs/examples/templates/) — starter templates for common Kybernetix workspaces.
- [Original prompt](DESIGN.md) — the handoff document that started the conversation. Kept for provenance.

## Install (development)

```bash
uv sync                       # create venv, install deps
uv run brunch --help          # exercise the CLI in the dev venv
uv run br --help              # short alias
```

For end-user install (once published or from a path):

```bash
uv tool install .             # registers brunch and br on PATH
```

## Concepts in 30 seconds

- A **workspace** is a directory of co-located git worktrees, one per repo, with a `brunch.toml` manifest at its root.
- A **workspace set** is a directory of workspaces, with a `brunch-set.toml` at its root.
- Canonical clones live ghq-style under `<root>/<forge>/<org>/<repo>` (default root: `~/repos/brunch`). brunch never clones — it expects clones to be there.
- Operating mode (workspace vs set) is decided by walk-up discovery from `cwd`.

See [`docs/initial-design.md`](docs/initial-design.md) for everything else.
