# Getting started with brunch

A guided tour from installation to a first workspace and back to a clean
machine. For the full design rationale, see [`docs/initial-design.md`](initial-design.md).

## What brunch is

A small CLI that sets up **multi-repo task workspaces**: directories containing
one git worktree per repo, operated on as a unit. Brunch sits on top of
`git worktree` as a cooperative semantic layer — it never replaces git's own
state, just orchestrates around it.

Three use cases motivate it:

1. **A single task that spans multiple repos.** Backend + frontend on the same
   task branch, in one folder. One command to set up; one to tear down.
2. **Shape-up cycle prep / exploration.** A broad theme broken into N
   subtasks, each its own workspace, grouped under one parent directory
   ("workspace set") so an agent can reason across them.
3. **Agent-prepared workspaces.** Give an agent permission to invoke brunch
   and a short prompt; it sets up the workspace before exploration starts.

## Installing

```bash
git clone <repo-url> brunch && cd brunch
uv tool install .                      # registers `brunch` and `br` on PATH
brunch --version                       # confirm install
```

Both `brunch` and the short alias `br` are first-class — pick whichever your
fingers prefer.

## Prerequisites: where canonical clones live

Brunch never clones repositories. It assumes well-formed canonical clones
already exist on disk, laid out **ghq-style**:

```
<root>/<forge_id>/<organisation>/<repo>
```

The default `<root>` is `~/repos/brunch`. Override via
`~/.config/brunch/config.toml`:

```toml
root          = "~/repos/kybernetix/clones"
default_forge = "github.com"

[forges.github_com]
base_url = "https://github.com"
```

To populate that tree, use any of:

```bash
gh repo clone kybernetix/backend ~/repos/kybernetix/clones/github.com/kybernetix/backend
# or
ghq get github.com/kybernetix/backend  # if you use ghq with the matching root
```

Brunch will tell you exactly where it expects a clone if it can't find one,
so you don't have to compute the path by hand.

## A guided tour

This is the smallest end-to-end story: a task touching two repos.

### 1. Create the workspace

```bash
cd ~/tasks       # wherever you keep them — brunch doesn't care
brunch init task-1234-billing-flow
```

You now have:

```
task-1234-billing-flow/
└── brunch.toml          # {name = "task-1234-billing-flow"}
```

### 2. Add the repos you need

```bash
cd task-1234-billing-flow
brunch add kybernetix/backend            # branch defaults to workspace name
brunch add kybernetix/frontend
```

Each `add` invocation:

- resolves the canonical clone via the ghq-style path;
- pre-flights branch + worktree conflicts;
- runs `git worktree add` against the canonical;
- appends a `[[repo]]` entry to `brunch.toml`.

You now have:

```
task-1234-billing-flow/
├── brunch.toml
├── backend/        # git worktree on `task-1234-billing-flow`, from main
└── frontend/       # git worktree on `task-1234-billing-flow`, from main
```

### 3. Inspect

```bash
brunch status            # Rich table
brunch status --json     # structured output for agents / pipes
```

Make a change in one worktree and re-run `status` — uncommitted/untracked
markers update accordingly.

### 4. Cross-repo operations

Fan out across all repos in one command:

```bash
brunch fetch                         # git fetch in each repo (skipped where no remote)
brunch pull                          # git pull in each repo
brunch rebase                        # per-repo fetch + rebase onto each entry's base
brunch rebase --onto wip-branch      # rebase each worktree onto a sibling branch
brunch rebase --no-fetch             # skip the pre-rebase fetch
brunch rebase --continue-on-error    # don't stop at the first conflict
brunch foreach -- pnpm install       # run a command in each repo's worktree
brunch foreach --json -- pytest      # capture per-repo output as structured JSON
```

`brunch rebase` prefers `origin/<base>` when it exists (so a remote-tracking
ref is the freshest target), falling back to the local `<base>` branch
otherwise. Conflicts leave that repo's rebase in progress; resolve in the
worktree, then `git rebase --continue` (or `--abort`).

`brunch foreach` streams output live by default and captures per-repo with
`--json`. Use `--` to separate options for the foreach command from options
for the user's command (e.g. `brunch foreach -- pnpm -F backend lint`).

### 5. Diagnose

```bash
brunch fsck              # eight checks: canonicals, worktrees, drift, dangling refs, ...
brunch fsck --json
```

`fsck` is non-destructive. `fsck --fix` (M5) will safely prune dangling
worktree references; for now it's a no-op notice.

### 6. Tear down

```bash
brunch rm                # refuses if any worktree is dirty or has unpushed work
brunch rm --dry-run      # show what would be removed
brunch rm --force        # archive everything first, then remove
```

`brunch rm` walks each repo in the manifest, asks git to remove each
worktree, then `rmtree`s the workspace directory. Branches are left in
the canonical clones — worktrees are cheap to recreate.

With `--force`, the entire workspace directory is archived to
`~/.local/share/brunch/archives/<name>-<UTC-timestamp>.tar.gz` *before*
any destructive action — if you removed something you needed back, just
untar the archive.

**Safety contract.** brunch only ever deletes its own marker file
(`brunch.toml`), the worktrees declared in it, and the workspace
directory itself — and only if it ends up empty. Anything else under
the workspace root (sibling dirs, dotfiles, nested git repos, symlinks)
is preserved; the outcome is reported as `partial` with the surviving
items listed. To fully clean up afterwards, review the preserved items
and `rm -rf <workspace>` manually if you really want them gone. See
[`initial-design.md §7.5`](initial-design.md) for the full contract.

## Bringing an existing folder under brunch

Already have a folder of worktrees you assembled by hand? Adopt it:

```bash
cd ~/tasks/tech-1796-tweaks
brunch adopt                  # adopts cwd; workspace name = directory name
brunch adopt --dry-run        # preview the inferred manifest first
brunch adopt /path/to/folder  # adopt a specific path
brunch init <name> --adopt -p <parent>   # synonym
```

What adopt does, concretely:

1. Walks the direct children of the target. For each subdir whose `.git`
   is a *file* (worktree marker, not a regular clone), it reads the gitdir
   pointer to find the canonical clone, reverse-resolves the canonical
   against your configured `root` to recover `<forge>/<org>/<repo>`, and
   reads the worktree's current branch.
2. Writes `brunch.toml` listing each discovered repo. `base` is defaulted
   to `"main"` for every entry — review and edit if your worktrees were
   branched off something else.
3. Runs `brunch sync` and `brunch fsck` against the new manifest to
   confirm everything looks right. Both should be clean immediately
   after adoption.

Adopt is conservative: any per-worktree problem (canonical outside the
configured root, broken gitdir pointer, detached HEAD, duplicate short
name) aborts the whole adoption with a clear error. `brunch.toml` is
never written in that case. Sibling files/dirs that aren't worktrees are
silently left in place — adopt only ever creates one file.

## Workspace sets

When a task is broad enough to span multiple workspaces — a shape-up cycle's
subtasks, a refactor that hops between teams, an agent exploring related
threads — group them under a workspace **set**. A set is a directory with a
`brunch-set.toml` marker; its members are direct child workspaces.

```bash
brunch init 2026-Q2_billing-overhaul --set      # creates the set directory + marker
cd 2026-Q2_billing-overhaul
brunch init task-1234-api -t kybernetix-fullstack     # member workspace
brunch init task-1235-dashboard -t kybernetix-fullstack
```

You now have:

```
2026-Q2_billing-overhaul/
├── brunch-set.toml
├── task-1234-api/
│   ├── brunch.toml
│   └── …worktrees…
└── task-1235-dashboard/
    ├── brunch.toml
    └── …worktrees…
```

From the set root, every command fans out across all members:

```bash
brunch status            # aggregated per-member status
brunch fsck              # per-member health checks
brunch fetch / pull      # fan out fetches/pulls across all repos of all members
brunch rebase            # per-member rebase semantics
brunch foreach -- pytest # run a command in every repo of every member
brunch rm --force        # single set-level archive, then per-member removal
```

`brunch add` and `brunch sync` are workspace-only — at the set root they
error with a clear message asking you to cd into a child or pass `-w
<path>`.

The deletion safety contract from §6 extends to the set root: members
that end up `partial` (because they had unknown content) survive, and
their dirs are preserved at the set level too. Unknown content at the
set root (notes, scratch files) is also preserved.

## Shortcut: workspace from a template

Templates live as plain TOML files at `~/.config/brunch/templates/<id>.toml`.
A few starter templates for a fictional Kybernetix product live under
[`docs/examples/templates/`](examples/templates/); copy any of them into your
config dir to make them available:

```bash
mkdir -p ~/.config/brunch/templates
cp docs/examples/templates/kybernetix-fullstack.toml ~/.config/brunch/templates/
```

Then:

```bash
brunch init task-1234-billing -t kybernetix-fullstack
```

Brunch materialises the manifest from the template (defaulting each repo's
branch to the workspace name and base to `main`), creates the workspace
directory, and immediately syncs to materialise the worktrees — equivalent to
running `init` + N × `add` in one go.

See [`docs/examples/templates/README.md`](examples/templates/README.md) for
the bundled examples.

## JSON output for agents

Every read/mutation command supports `--json`. The shape is stable and
Pydantic-driven:

```bash
brunch status --json
brunch fsck --json
brunch sync --json --dry-run
brunch fetch --json
brunch rebase --json --no-fetch
brunch foreach --json -- pytest -q
```

The output is suitable for piping into `jq` or for parsing inside an agent's
tool-use loop.

## Where to go next

- **Functional design**: [`docs/initial-design.md`](initial-design.md) —
  concepts, decisions log, alternatives considered, deferred work, milestones.
- **Original prompt**: [`DESIGN.md`](../DESIGN.md) — the conversation that
  started the project, kept for provenance.
- **Example templates**: [`docs/examples/templates/`](examples/templates/).
