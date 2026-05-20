# 5. Commit

brunch keeps commits **independent per repo**. There's no cross-repo
atomic-commit story (and intentionally so — that would muddle git's
own concurrency model). Each repo gets its own commit, written from
within its own worktree.

## The basic flow

```bash
brunch foreach -- git add -A
brunch foreach -- git status --short
```

Then either commit in each repo with a per-repo message via `foreach`:

```bash
brunch foreach -- git commit -m "feat: add /api/v1/users/export CSV endpoint"
```

…or — usually friendlier — `cd` into the worktrees and write proper
commit messages by hand:

```bash
(cd backend  && git commit -m "feat: add /api/v1/users/export CSV endpoint")
(cd frontend && git commit -m "feat(users): add 'Download CSV' button")
```

## Why one message per repo

The first commit explains the API change in the backend's history; the
second explains the UI change in the frontend's history. Each will be
reviewed in a separate PR, against a different reviewer pool, against a
different test pipeline. Two messages, two histories, one task.

If you later need to identify "all the commits for task TASK-1234", the
branch name already does that — searching `git log --branches=task-1234-*`
across each repo gives you the slice.

## A workspace-level commit log

`brunch foreach -- git log --oneline -3` shows the last few commits per
repo so you can sanity-check what landed where before pushing:

```text
==> backend
abc1234 feat: add /api/v1/users/export CSV endpoint
9876def chore: bump fastapi minor
12abc34 docs: tidy README

==> frontend
def5678 feat(users): add 'Download CSV' button
fed9876 chore: dependency bumps
8765abc fix(ui): button padding
```

## The recorded cast

<div class="brunch-cast" data-cast="../../assets/casts/05-commit.cast"></div>

Next: **[6. Push →](06-push.md)**
