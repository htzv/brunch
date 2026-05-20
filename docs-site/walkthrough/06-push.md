# 6. Push

One push per repo, one command.

```bash
brunch foreach -- git push -u origin HEAD
```

`-u origin HEAD` sets the upstream the first time and pushes the
current branch by name. Subsequent pushes are just
`brunch foreach -- git push`.

What the output looks like (live-streamed by `foreach`):

```text
==> backend
Enumerating objects: 12, done.
…
remote: Create a pull request for 'task-1234-add-export' on GitHub:
remote:   https://github.com/acme/backend/pull/new/task-1234-add-export
To github.com:acme/backend.git
 * [new branch]      HEAD -> task-1234-add-export
branch 'task-1234-add-export' set up to track 'origin/task-1234-add-export'.

==> frontend
…
remote: Create a pull request for 'task-1234-add-export' on GitHub:
remote:   https://github.com/acme/frontend/pull/new/task-1234-add-export

foreach  task-1234-add-export
  OK     backend   (acme/backend) (exit 0)
  OK     frontend  (acme/frontend) (exit 0)
```

!!! brunch-tip "Pushing only specific repos"
    `brunch foreach` always runs in every repo. To push only one,
    `cd` in or use `-w <member-path>` when the workspace is inside a
    [workspace set](../ref/initial-design.md#42-brunch-settoml-set-manifest).
    For a single workspace, plain `cd` is the simplest path.

## After the push

`brunch status` now shows the push reflected:

```bash
brunch status
```

```text
  ┃ repo     ┃ branch               ┃ state ┃ ahead/behind ┃
  │ backend  │ task-1234-add-export │ clean │            - │
  │ frontend │ task-1234-add-export │ clean │            - │
```

The `ahead/behind` column is `-` (no divergence) because we just pushed
exactly what's local.

## The recorded cast

<div class="brunch-cast" data-cast="../../assets/casts/06-push.cast"></div>

Next: **[7. Open PRs →](07-pr.md)**
