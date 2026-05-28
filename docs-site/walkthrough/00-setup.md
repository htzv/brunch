# 0. Setup

One-time work: install brunch, point it at where you keep canonical
clones, and drop a template in place.

## Install brunch

```bash
uv tool install brunch
brunch --version
```

`uv tool install` puts both `brunch` and the short alias `br` on your
`$PATH` inside a tool-isolated venv. Either invocation works
interchangeably; we'll use `brunch` in the rest of the tutorial for
clarity.

## Configure the canonical-clone root

brunch never clones repos. It expects them already laid out **ghq-style**
at `<root>/<forge>/<org>/<repo>` (the same convention as
[ghq](https://github.com/x-motemen/ghq) or `GOPATH/src/<importpath>`):

```
~/repos/brunch/
└── github.com/
    └── kybernetix/
        ├── backend/
        └── frontend/
```

Tell brunch where this root lives via `~/.config/brunch/config.toml`:

```toml title="~/.config/brunch/config.toml"
root          = "~/repos/brunch"
default_forge = "github.com"
```

To populate the tree, use whichever tool you prefer:

=== "ghq"

    ```bash
    ghq get github.com/kybernetix/backend
    ghq get github.com/kybernetix/frontend
    ```

=== "gh CLI"

    ```bash
    gh repo clone kybernetix/backend  ~/repos/brunch/github.com/kybernetix/backend
    gh repo clone kybernetix/frontend ~/repos/brunch/github.com/kybernetix/frontend
    ```

=== "plain git"

    ```bash
    git clone git@github.com:kybernetix/backend.git  ~/repos/brunch/github.com/kybernetix/backend
    git clone git@github.com:kybernetix/frontend.git ~/repos/brunch/github.com/kybernetix/frontend
    ```

## Install a workspace template

A *template* is a partial brunch manifest at
`~/.config/brunch/templates/<id>.toml`. For our two-repo scenario:

```toml title="~/.config/brunch/templates/kybernetix-fullstack.toml"
description = "Backend + frontend for typical Kybernetix fullstack tasks."

[[repo]]
repo = "kybernetix/backend"

[[repo]]
repo = "kybernetix/frontend"
```

That's it — no `name`, no `branch` (it defaults to the workspace name at
materialisation time), no `base` (defaults to `"main"`). The template
just declares "this kind of workspace includes these two repos."

!!! tip "Starter templates"
    The repository ships starter templates at
    [`docs/examples/templates/`](https://github.com/htzv/brunch/tree/main/docs/examples/templates) —
    `kybernetix-fullstack`, `kybernetix-billing`, `kybernetix-data-pipeline`,
    `kybernetix-platform-ops`. Copy any of them into
    `~/.config/brunch/templates/` and they're ready to use, or use them
    as templates (no pun intended) for your own org's set.

## The recorded cast

<div class="brunch-cast" data-cast="../../assets/casts/00-setup.cast"></div>

Setup is done. **[1. Create a workspace →](01-create.md)**
