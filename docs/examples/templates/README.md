# Example templates

A handful of starter templates for common Kybernetix workspaces. Copy any of them
into `~/.config/brunch/templates/` to make them available as
`brunch init <name> -t <template-id>`.

## Installing

```bash
mkdir -p ~/.config/brunch/templates
cp docs/examples/templates/kybernetix-fullstack.toml ~/.config/brunch/templates/
# repeat for any others you want
```

There is no `brunch templates list/install/copy` command — templates are just
TOML files in a known directory. `ls ~/.config/brunch/templates/` is the
discovery tool.

## Available templates

| Template id | Repos included | Use when |
|---|---|---|
| `kybernetix-fullstack` | `backend`, `frontend` | A task touching the user-facing platform end to end. |
| `kybernetix-billing` | `backend`, `backend`, `backend` | A billing task that may need API + report + workspace integration. |
| `kybernetix-data-pipeline` | `data-pipelines`, `data-pipelines`, `backend` | A data pipeline / ingestion pipeline task. |
| `kybernetix-platform-ops` | `devops`, `backend`, `backend` | Infra / admin tooling work that touches deployment + admin CLI + backend. |

## How templates work

A template is a partial workspace manifest. At `brunch init` time:

- The template's `name` (if any) is overridden by the workspace name you pass.
- Each `[[repo]]` entry's `branch` defaults to the workspace name unless set.
- Each `[[repo]]` entry's `base` defaults to `"main"` unless set.

So an empty-ish template lets you write `brunch init task-1234-x -t kybernetix-fullstack`
and get `task-1234-x` checked out across both `backend` and `frontend`, each on
a `task-1234-x` branch starting from `main`.

## Notes

- Repo specs use the short `<org>/<name>` form; `org` defaults to whatever
  `default_forge` resolves in your `~/.config/brunch/config.toml` (default
  `github.com`). All Kybernetix repos live under
  [`kybernetix`](https://github.com/kybernetix) on GitHub.
- Make sure the corresponding canonical clones exist under your configured
  `root` before invoking `brunch init` — brunch never clones. See
  [`docs/getting-started.md`](../../getting-started.md#prerequisites-where-canonical-clones-live).
- These templates intentionally do not pin commits or tags. Pinning is parked
  for a later milestone; v1 manifests record *intent* (branch / base), never
  *state*.
