# 4. Verify

Run each repo's test suite in turn, then confirm the workspace is still
healthy.

## Per-repo tests

`brunch foreach` runs a command in every repo of the workspace, with
each repo's name as a header, and aggregates exit codes:

=== "Python backend"

    ```bash
    brunch foreach -- pytest -q
    ```

=== "TypeScript frontend"

    ```bash
    brunch foreach -- pnpm test
    ```

=== "Mixed (one command per stack)"

    ```bash
    # If the projects use different test runners, two passes is fine:
    brunch foreach -w backend  -- pytest -q
    brunch foreach -w frontend -- pnpm test
    ```

The non-aggregated version of the third form uses `-w` to target a
specific workspace; you wouldn't normally need it inside a single
workspace, but it's there for set-mode use.

Sample output (per-repo headers + final aggregate):

```text
==> backend  (/home/you/.../task-1234-add-export/backend)
.....                                                  [100%]
5 passed in 0.42s

==> frontend  (/home/you/.../task-1234-add-export/frontend)
Test Suites: 3 passed, 3 total
Tests:       18 passed, 18 total

foreach  task-1234-add-export
         path    /home/you/.../task-1234-add-export
         command ['pytest', '-q']

  OK         backend  (acme/backend) (exit 0)
  OK         frontend  (acme/frontend) (exit 0)
```

If any repo's command exits non-zero, the run stops by default. Pass
`--continue-on-error` to fan out across everything regardless.

## Confirm the workspace is still clean

`fsck` is non-destructive — run it any time you suspect drift:

```bash
brunch fsck
```

…and `status` shows the working-tree picture:

```bash
brunch status
```

The branch column should still read `task-1234-add-export`. Uncommitted
or untracked changes will surface as `uncommitted` / `untracked` in the
state column — useful before commit, when you want a single-screen
overview of "what did the agent leave behind".

## The recorded cast

<div class="brunch-cast" data-cast="../../assets/casts/04-verify.cast"></div>

Next: **[5. Commit →](05-commit.md)**
