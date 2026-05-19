I want to build a small FLOSS CLI tool for managing **task workspaces**: directories that each contain git worktrees of multiple repositories, operated on as a unit. Think of it as a worktree-aware spiritual successor to [myrepos (`mr`)](https://myrepos.branchable.com/), shaped around an agentic-coding workflow (e.g. Claude Code).

## Background and motivation

When working on a task (often tracked as a Linear ticket), I need several repos checked out together — for example, a backend repo and a frontend repo — so I can read across them, modify in lockstep, and let an agent reason about cross-repo concerns like "how does the frontend call this API endpoint I'm changing?".

I've been doing this manually with `git worktree add` per repo, one folder per task. It works, but there's friction:

- Setting up a new task = N manual `git worktree add` invocations.
- No single source of truth for "what does this task workspace consist of."
- Tearing down, syncing, or recreating a task workspace is fiddly.
- I want to do things like "rebase this task's branch in repo A onto another task's WIP branch in repo A" without hand-rolling it each time.

The worktree property is important: everything stays linked to the canonical clone, commits cherry-pick cleanly across task workspaces, disk usage stays sane, and branch state is shared.

The whole setup should be extremely cheap to maintain, and it may be useful for Claude or another agent to be able to prepare a task workspace for a new task without needing to set it up manually (an agent could be given the permission to use the tool, with clear instructions and harnesses).

It should be so cheap that I could even prepare a broad task in Linear for a shapeup cycle about to start, break it down into subtasks, and ask an agent to look at the task and subtasks and prepare a composite workspace (made up of multiple of these task-related workspaces, all coherently managed as a single set) and run exploratory sessions (feasibility, exploration, functional design, thinking about tests, caveats and so on) - and then tear the composite workspace down after we finish exploring things and are done producing documentation (through which I may then update Linear tasks or create new implementation ones from initial exploratory tasks).

## Design sketch (open to revision)

**Concept.** A _task workspace_ is a directory containing one subdirectory per repo, each being a git worktree. A manifest file at the workspace root describes it.

**Manifest format.** TOML, something like:

```toml
name = "PROJ-123-new-billing-flow"
description = "Add usage-based billing to the API and surface it in the dashboard"

[[repo]]
name = "api"
source = "~/src/api"          # path to canonical clone (the "main" worktree)
branch = "proj-123-billing"    # branch to check out in this worktree; created if absent
base = "main"                  # what to branch from if creating

[[repo]]
name = "dashboard"
source = "~/src/dashboard"
branch = "proj-123-billing"
base = "main"
```

Additionally, we should be able to create workspace _templates_ - predefined sets of repos to check out as worktrees for each new task workspace, without having to specify each of them in the task's TOML, nor to specify details such as branch names and base branches - in practice, I should even be able to just run a command to create a workspace from a template without even having a TOML file for the task.

Besides these workspaces, as above, we also need to be able to create workspace sets, where each individual workspace maps to a Linear task (or in some cases just some kind of placeholder if I don't have a task in Linear for a task or subtasks or related task: in these cases I normally use folder names such as `YYYY-MM_whatever-short-description`), and the agent would then have access to _the parent workspace set's root folder_ so that it can operate throughout the different workspaces under it, for example if needing to verify something for a task with context gained while exploring another task.

**CLI surface (rough first cut):**

- `tw init <name> [--from <template_id>]` — create a new task workspace directory + empty manifest, optionally from a workspace template
- `tw add <repo-source> [--branch X --base Y]` — add a repo to the current workspace's manifest and create its worktree
- `tw sync` — make the on-disk worktrees match the manifest (create missing, warn on drift)
- `tw status` — `git status` across all repos, summarized
- `tw foreach <cmd>` — run a shell command in each repo (à la `mr run`)
- `tw fetch` / `tw pull` — across all repos
- `tw rm` — remove the workspace, properly pruning worktrees from the canonical clones
- `tw list` — list known task workspaces (probably from a registry file in `~/.config/tw/`)

`--dry-run` switches throughout. Ability to get config on stdin and to output results to stdout so that different such commands could be piped together. Also maybe a command to archive a workspace or workspace set (also used before a `tw rm --force`, transparently, for an extra safety measure).

The CLI surface for workspace sets should be similar, without adding too much complexity and special cases or verbosity.

**Open design questions to discuss before coding:**

1. Language. I'm leaning Rust or Go for a single static binary; Python is fine too if it keeps things simple. What do you recommend given the scope?

I'd go for Rust. One single static binary is a dream. We are not a Rust shop, but this should be a fairly simple codebase and with agentic help we should be able to manage. A good pragmatic option may be to go with Python with Typer as prototyping stage, since the team is experienced with

2. How to discover the canonical clone for a repo — explicit `source` path, or a configurable search path, or both?

Maybe a main catalogue with canonical clones of key repos from the GH organization (in parallel we are working on a tool to keep GH repo catalog up to date with metadata curated in a Notion db)

3. Should the manifest pin commits (for reproducibility) or just branches (for liveness)? Probably branches with optional commit pinning.

Branches with optional pinning.

4. Registry of workspaces: file in `~/.config/tw/`? Or just "any directory with a `tw.toml` is a workspace" with no central registry?

I'd go for `~/.config/tw/`.

5. How to handle `tw rm` safely when there are uncommitted changes or unpushed commits in any of the worktrees.

Forbid. Expose a `tw rm --force` option that bypasses the safety checks, but always takes an archive of everything first (e.g. in `~/.local/share/tw/archives/`).

## What I'd like from you

Start by pushing back on or refining the design above — point out anything dumb, missing, or over-engineered. Then propose a concrete plan: language choice, project layout, dependency choices, and a milestone breakdown (MVP first, then niceties). Once we agree on that, we'll implement incrementally, smallest useful slice first.

Don't write code yet on the first turn. Let's nail the design.
