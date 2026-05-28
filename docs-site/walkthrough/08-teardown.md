# 8. Tear down

PRs are open and reviewed; you don't need the workspace any more. Time
to clean up.

```bash
cd ..
brunch rm -w task-1234-add-export
```

If everything in the workspace is clean (pushed, no untracked files),
`rm` removes the worktrees, prunes the canonicals' dangling refs, and
deletes the workspace directory:

```text
rm  task-1234-add-export
    path  /home/you/tasks/task-1234-add-export

  REMOVED       backend   (kybernetix/backend)
                removed worktree at .../task-1234-add-export/backend
  REMOVED       frontend  (kybernetix/frontend)
                removed worktree at .../task-1234-add-export/frontend

removed workspace .../task-1234-add-export
```

**Branches survive.** brunch never deletes branches — they stay in the
canonical clones. You can `git -C ~/repos/brunch/github.com/kybernetix/backend
branch --list task-1234-*` and they'll be right there. Worktrees are
cheap to recreate; branches are where the work lives.

## The safety contract

`brunch rm` never destroys anything outside its manifest. If you left
something extra at the workspace root (a stray scratch file, a note, an
unrelated git repo), rm preserves it and reports a `partial` outcome:

```text
  preserved 1 non-manifest item in .../task-1234-add-export:
    - scratch.md

workspace dir preserved at .../task-1234-add-export
hint: brunch only deletes what the manifest declares; review the items
above and `rm -rf <path>` manually if you really want everything gone.
```

This is the [safety contract](../ref/initial-design.md#deletion-safety-contract)
spelled out in the design doc. brunch deletes only:

1. its own marker file (`brunch.toml`);
2. directories the manifest declares as worktrees, via `git worktree
   remove` (never `shutil.rmtree`);
3. the workspace directory itself, **only when it ends up empty** after
   (1) + (2).

## The dirty case: `--force`

If the workspace has uncommitted work you've decided you don't want, or
local-only branches with unpushed commits, `rm` refuses by default:

```text
refused: workspace has at-risk repos:

  backend  (kybernetix/backend)
           uncommitted changes, 2 unpushed commit(s)

hint: commit/push/clean the worktrees, or pass --force to archive
everything first.
```

`--force` overrides the refusal **but archives the entire workspace
first**:

```bash
brunch rm -w task-1234-add-export --force
```

```text
  archived to ~/.local/share/brunch/archives/task-1234-add-export-20260520T143042Z.tar.gz
  REMOVED       backend   (kybernetix/backend)
  REMOVED       frontend  (kybernetix/frontend)
removed workspace …
```

The archive is a fat tar.gz of the whole directory. If you change your
mind, `tar -xzf` it anywhere and you have the workspace back, sibling
content and all.

## The recorded cast

<div class="brunch-cast" data-cast="../../assets/casts/08-teardown.cast"></div>

## What's next

You've taken a complete task end to end: create → work → verify →
commit → push → review → tear down. The reference docs go deeper:

- **[Functional design](../ref/initial-design.md)** — every decision and
  the rationale behind it.
- **[Getting started](../ref/getting-started.md)** — the prose version
  of the prerequisites and a longer walk-through.
- **Workspace sets** — when one task isn't enough and you want to group
  several workspaces under one set (a shape-up cycle, an exploration
  across related tickets). The same nine commands fan out at set scope;
  see [§6.3 of the design doc](../ref/initial-design.md#63-set-mode-semantics).

Feedback, bug reports, and contributions welcome at
[htzv/brunch](https://github.com/htzv/brunch).
