# brunch

**Mise en place for git worktree-based multi-repo task workspaces.**

A small CLI that sets up a *task workspace*: one directory containing one
git worktree per repo, operated on as a unit. Where `git worktree`
manages multiple worktrees inside a single repo, **brunch** does the
same trick across multiple repos at once, so a task that touches the
backend and the frontend lives in a single directory you can hand to an
agent or `cd` into.

```
~/repos/kybernetix.example/tasks/task-1234-add-export/
├── brunch.toml
├── backend/       # git worktree of acme/backend on `task-1234-add-export`
└── frontend/      # git worktree of acme/frontend on `task-1234-add-export`
```

## Why

- **Set up once, command across everything.** `brunch status`, `brunch
  rebase`, `brunch foreach -- pytest` fan out across every repo in the
  workspace.
- **Agent-friendly.** Hand the workspace directory to Claude Code (or
  any agent that can read filesystem context) and it has the full
  cross-repo picture in one place.
- **Cheap teardown.** `brunch rm` cleans up worktrees from each canonical
  clone; `brunch rm --force` archives everything first so nothing is
  ever destroyed without a snapshot.
- **Cooperative, not invasive.** brunch never shadows git's own state —
  it relies on `git worktree`'s built-in machinery underneath.

## Take the tour

The fastest way in is the **[walkthrough](walkthrough/index.md)** — one short
asciinema-recorded step per page, taking a complete task end to end:
create a workspace from a template, hand the work to Claude Code, run
tests, commit, push, open PRs, and tear down.

If you'd rather read the design and conventions first, see the
**[functional design](ref/initial-design.md)** or the
**[getting-started reference](ref/getting-started.md)**.

## Where it came from

The original prompt that started the project lives in
[`DESIGN.md`](https://github.com/htzv/brunch/blob/main/DESIGN.md). It
captures the working notes — the name (`brunch`) is a small wink at
*mise en place* and a pun on `branch`.
