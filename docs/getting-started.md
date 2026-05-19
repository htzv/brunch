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

The default `<root>` is `~/repos/tw`. Override via
`~/.config/brunch/config.toml`:

```toml
root          = "~/repos/kybernetix.example/clones"
default_forge = "github.com"

[forges.github_com]
base_url = "https://github.com"
```

To populate that tree, use any of:

```bash
gh repo clone kybernetix/backend ~/repos/kybernetix.example/clones/github.com/kybernetix/backend
# or
ghq get github.com/kybernetix/backend  # if you use ghq with the matching root
```

Brunch will tell you exactly where it expects a clone if it can't find one,
so you don't have to compute the path by hand.

## A guided tour

This is the smallest end-to-end story: a task touching two repos.

### 1. Create the workspace

```bash
cd ~/repos/kybernetix.example/tasks       # wherever you keep them — brunch doesn't care
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

### 4. Cross-repo operations (M3 — coming)

Once M3 lands you'll be able to run `brunch fetch`, `brunch pull`,
`brunch rebase`, and `brunch foreach <cmd>` to fan out across all repos in
the workspace.

### 5. Diagnose

```bash
brunch fsck              # eight checks: canonicals, worktrees, drift, dangling refs, ...
brunch fsck --json
```

`fsck` is non-destructive. `fsck --fix` (M5) will safely prune dangling
worktree references; for now it's a no-op notice.

### 6. Tear down

```bash
brunch rm                # M4 — refuses if anything is dirty
brunch rm --force        # M4 — archives to ~/.local/share/brunch/archives/ first
```

(M4 is next; until then, `rm -rf task-1234-billing-flow/` plus
`git -C <canonical> worktree prune` does the job.)

## Shortcut: workspace from a template

Templates live as plain TOML files at `~/.config/brunch/templates/<id>.toml`.
A few starter templates for Kybernetix work live under
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

Every read command supports `--json`. The shape is stable and Pydantic-driven:

```bash
brunch status --json
brunch fsck --json
brunch sync --json --dry-run
```

The output is suitable for piping into `jq` or for parsing inside an agent's
tool-use loop.

## Where to go next

- **Functional design**: [`docs/initial-design.md`](initial-design.md) —
  concepts, decisions log, alternatives considered, deferred work, milestones.
- **Original prompt**: [`DESIGN.md`](../DESIGN.md) — the conversation that
  started the project, kept for provenance.
- **Example templates**: [`docs/examples/templates/`](examples/templates/).
