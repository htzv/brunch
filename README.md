# brunch

Brunch gives each task its own directory, with one git worktree for every repo the
task touches. The worktrees share one branch name, sit side by side, and can be
checked, fetched and rebased together with one command. It is for people, and
coding agents, who often change several repos for one piece of work.

## Quick start

```bash
br init add-export                       # new workspace: ./add-export
cd add-export
br add example/backend                   # worktree ./backend on branch add-export
br add github.com/example/frontend       # worktree ./frontend on branch add-export
br status                                # one table for all repos
br rm                                    # remove the workspace when you are done
```

`br` and `brunch` are the same command. `br --help` and `br <command> --help` list
every command and flag.

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
uv tool install git+https://github.com/htzv/brunch
br --version
```

## Develop

```bash
uv sync --extra dev
uv run br --help
```

Coding agents working on brunch, or using it, should read [AGENTS.md](AGENTS.md)
first.

## More

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
