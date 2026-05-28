# Example templates

A handful of starter templates for common Kybernetix workspaces. Copy any
of them into `~/.config/brunch/templates/` to make them available as
`brunch init <name> -t <template-id>`.

The fictional product on display here is **kbrntx** — a multitenant web
app from a fictional company called Kybernetix. Its repos use the stock
shape you'd expect from a product of that flavour: `backend`, `frontend`,
`data-pipelines`, `devops`, `oci-base-images`. Use these as inspiration
for your own templates.

## Installing

```bash
mkdir -p ~/.config/brunch/templates
cp docs/examples/templates/kybernetix-fullstack.toml ~/.config/brunch/templates/
# repeat for any others you want
```

There is no `brunch templates list/install/copy` command — templates are
just TOML files in a known directory. `ls ~/.config/brunch/templates/`
is the discovery tool.

## Available templates

| Template id | Repos included | Use when |
|---|---|---|
| `kybernetix-fullstack` | `backend`, `frontend` | A task touching the user-facing platform end to end. |
| `kybernetix-billing` | `backend`, `frontend`, `data-pipelines` | A billing/quotas task that spans tenant API, dashboards, and usage rollup workers. |
| `kybernetix-data-pipeline` | `data-pipelines`, `backend` | A data-engineering task that needs backend coordination (schemas, APIs). |
| `kybernetix-platform-ops` | `devops`, `oci-base-images`, `backend` | Infra / base-image work that needs coordinated backend changes. |

## How templates work

A template is a partial workspace manifest. At `brunch init` time:

- The template's `name` (if any) is overridden by the workspace name you pass.
- Each `[[repo]]` entry's `branch` defaults to the workspace name unless set.
- Each `[[repo]]` entry's `base` defaults to `"main"` unless set.

So an empty-ish template lets you write
`brunch init task-1234-x -t kybernetix-fullstack` and get `task-1234-x`
checked out across both `backend` and `frontend`, each on a `task-1234-x`
branch starting from `main`.

## Notes

- Repo specs use the short `<org>/<name>` form; `org` defaults to whatever
  `default_forge` resolves in your `~/.config/brunch/config.toml` (default
  `github.com`). Substitute your own org's repos when adapting for real
  work.
- Make sure the corresponding canonical clones exist under your configured
  `root` before invoking `brunch init` — brunch never clones. See
  [`docs/getting-started.md`](../../getting-started.md#prerequisites-where-canonical-clones-live).
- These templates intentionally do not pin commits or tags. Pinning is
  parked for a later milestone; v1 manifests record *intent* (branch /
  base), never *state*.
