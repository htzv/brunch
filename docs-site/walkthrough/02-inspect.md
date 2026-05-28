# 2. Inspect

Two read-only commands you'll lean on constantly.

## `brunch status`

`status` aggregates `git status` across every repo in the workspace:

```bash
cd task-1234-add-export
brunch status
```

You should see something like:

```text
workspace  task-1234-add-export
path       /home/you/tasks/task-1234-add-export
about      Backend + frontend for typical Kybernetix fullstack tasks.

  ┃ repo     ┃ branch               ┃ state ┃ ahead/behind ┃
  ╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━━━━━━┩
  │ backend  │ task-1234-add-export │ clean │            - │
  │ frontend │ task-1234-add-export │ clean │            - │
```

For machines (or `jq`), every read command supports `--json`:

```bash
brunch status --json | jq '.repos[].current_branch'
# "task-1234-add-export"
# "task-1234-add-export"
```

## `brunch fsck`

`fsck` runs eight health checks across the workspace: canonical clones
present, worktrees healthy, no dangling refs in canonicals, no drift
between manifest and reality, no rogue worktree subdirectories. It's
the equivalent of `git fsck` for the multi-repo layer brunch maintains.

```bash
brunch fsck
```

```text
workspace  task-1234-add-export
path       /home/you/tasks/task-1234-add-export

all checks passed
```

If something's off, fsck reports it with an actionable hint (e.g.
`worktree-missing` → "run brunch sync", `canonical-missing` → the exact
`gh repo clone` you'd run).

## The recorded cast

<div class="brunch-cast" data-cast="../../assets/casts/02-inspect.cast"></div>

Next: **[3. Hand off to Claude Code →](03-claude-code.md)**
