# 1. Create a workspace from a template

One command. Both worktrees materialise on a new branch.

```bash
cd ~/tasks
brunch init task-1234-add-export -t kybernetix-fullstack
```

What happens, in order:

1. brunch creates the directory `task-1234-add-export/`.
2. It reads `~/.config/brunch/templates/kybernetix-fullstack.toml`, fills in
   `name = "task-1234-add-export"`, and defaults each `[[repo]]`'s
   `branch` to the workspace name.
3. The resulting `brunch.toml` is written at the workspace root.
4. brunch immediately runs `sync` against the fresh manifest — which
   means `git worktree add -b task-1234-add-export …` against each
   canonical clone.
5. You end up with:

    ```
    task-1234-add-export/
    ├── brunch.toml
    ├── backend/      # worktree on task-1234-add-export, branched from main
    └── frontend/     # worktree on task-1234-add-export, branched from main
    ```

The resulting `brunch.toml`:

```toml title="task-1234-add-export/brunch.toml"
name = "task-1234-add-export"
description = "Backend + frontend for typical Kybernetix fullstack tasks."

[[repo]]
repo   = "kybernetix/backend"
branch = "task-1234-add-export"
base   = "main"

[[repo]]
repo   = "kybernetix/frontend"
branch = "task-1234-add-export"
base   = "main"
```

## The recorded cast

<div class="brunch-cast" data-cast="../../assets/casts/01-create.cast"></div>

!!! brunch-tip "Branch naming"
    The `task-1234-add-export` branch name was used as-is for both
    repos. This is the convention: one branch name across all repos in
    a workspace. If a repo needs a different branch, edit `brunch.toml`
    and re-run `brunch sync`.

!!! brunch-tip "Already have the worktrees built by hand?"
    Use [`brunch adopt`](../ref/getting-started.md#bringing-an-existing-folder-under-brunch)
    instead of `brunch init -t`. It reverse-resolves your existing
    worktrees against the configured `root` and writes a `brunch.toml`
    matching them.

Next: **[2. Inspect →](02-inspect.md)**
