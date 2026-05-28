# Walkthrough

A complete task, end to end, in nine short pages.

## The scenario

You've picked up **Linear ticket TASK-1234** — *Add a CSV export endpoint*.
It needs a new API route on the backend and a download button on the
frontend, and you want both repos checked out together so an agent (or
your own brain) can keep them in sync.

The repos in this tutorial belong to a fictional Kybernetix product —
`kybernetix/backend` (Python) and `kybernetix/frontend` (TypeScript).
Substitute your own org's repos and everything else stays the same.

## What you'll see

| Page | What happens |
|---|---|
| [0. Setup](00-setup.md) | One-time prep: install brunch, configure the canonical-clone root, install a template. |
| [1. Create a workspace](01-create.md) | `brunch init task-1234-add-export -t kybernetix-fullstack` — one command, both worktrees materialised. |
| [2. Inspect](02-inspect.md) | `brunch status` and `brunch fsck` to confirm the workspace looks right. |
| [3. Hand off to Claude Code](03-claude-code.md) | Start an agent session pointed at the workspace; it reasons across both repos. |
| [4. Verify](04-verify.md) | `brunch foreach -- pytest` (or `pnpm test`) runs the test suite in every repo. |
| [5. Commit](05-commit.md) | Per-repo commits via `brunch foreach -- git commit`. |
| [6. Push](06-push.md) | One push per repo, one command. |
| [7. Open PRs](07-pr.md) | One PR per repo via `gh`, kicked off from the workspace. |
| [8. Tear down](08-teardown.md) | `brunch rm` and the safety contract that keeps anything not in the manifest. |

Each page has the commands you'd run and a short asciinema cast of the
output. The casts are reproducible — see [Recording the
casts](../recording.md) for the script that generates them.

!!! info "Prerequisites for following along live"
    You need [`uv`](https://docs.astral.sh/uv/) (any recent version) and
    `git`. If you want the asciinema casts to match yours pixel-for-pixel,
    [`asciinema`](https://asciinema.org/) too. None of the demo steps
    touch a real remote — pushes/PRs go to bare local repos that pretend
    to be GitHub.

Onwards: [**0. Setup →**](00-setup.md)
