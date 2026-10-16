# brunch

> Mise en place for git worktree-based multi-repo task workspaces.
>
> — the author, as originally described

Brunch gives each task its own directory, with one git worktree for every repo the
task touches. By default the worktrees share one branch name, sit side by side, and
can be checked, fetched and rebased together with one command. It is for people,
and coding agents, who often change several repos for one piece of work.

As described at inception:

> A small CLI for setting up, synchronising, and tearing down **task workspaces** — directories of co-located git worktrees, one per repo, operated on as a unit.
> A worktree-aware spiritual successor to [myrepos (`mr`)](https://myrepos.branchable.com/), shaped around an agentic-coding workflow.

## Quick start

```bash
br init PROJECT-1234_add-export          # new workspace: ./PROJECT-1234_add-export
cd PROJECT-1234_add-export
br add example/backend                   # worktree ./backend, branch PROJECT-1234_add-export
br add github.com/example/frontend       # worktree ./frontend, same branch
br status                                # one table for all repos
br rm                                    # remove the workspace when you are done
```

The workspace name is also the default branch name. Naming it after a task id, as
above, makes the branches easy to trace back to the task.

`br` and `brunch` are the same command. `br --help` and `br <command> --help` list
every command and flag.

**Branches.** The same branch in every repo is what brunch expects, not something it
enforces. You can rename or switch the branch in one worktree. Brunch does not
stop you, but `br status`, `br sync` and `br fsck` then warn that the worktree's
branch differs from the one in `brunch.toml`. They do not change anything.

Brunch never clones. The repos must already be cloned at
`<root>/<forge>/<org>/<repo>`. The default root is `~/repos/brunch` and the default
forge is `github.com`. Change them in `~/.config/brunch/config.toml` (on Linux):

```toml
root = "~/repos/clones"
default_forge = "github.com"
```

## Install

Needs Python 3.11 or newer and [uv](https://docs.astral.sh/uv/).

```bash
uv tool install git+https://github.com/htzv/brunch@v0.1.0rc3
br --version
```

[Install](docs-site/install.md) also covers local checkouts, checking what you
have, and replacing an old install. [Update](docs-site/update.md) covers
upgrading.

## Develop

```bash
uv sync --extra dev
uv run br --help
```

Coding agents working on brunch, or using it, should read [AGENTS.md](AGENTS.md)
first.

## More

- [Changelog](CHANGELOG.md): what changed in each release.
- [Using brunch from a coding agent](docs-site/agents.md): a block of instructions to
  paste into an agent's prompt.
- [Walkthrough](docs-site/walkthrough/index.md): nine short pages that take one task
  from creation to teardown. Build the site with
  `uv sync --extra docs && uv run mkdocs serve`.
- [Getting started](docs/getting-started.md): a longer tour from install to a first
  workspace.
- [Design memo](docs/initial-design.md): what brunch does and why, with the
  alternatives that were considered.
- [Example templates](docs/examples/templates/): starter templates for a made-up
  product.
- [Original prompt](DESIGN.md): the handoff document the project started from.
