# brunch — initial functional design

This document captures the design we arrived at after several rounds of discussion. It explains **what brunch does**, **why each significant decision was made**, **what alternatives were considered**, and **what is deliberately left for later**. The companion `DESIGN.md` at the repo root preserves the original prompt that started the conversation.

---

## 1. Problem and motivation

When working on a task — typically tracked as a Linear ticket — several repos often need to be checked out together: backend, frontend, sometimes more. The goals are to read across them, modify in lockstep, and let an agent reason about cross-repo concerns ("how does the frontend call this API endpoint I'm changing?").

The current manual workflow is repetitive:

```bash
cd ~/repos/<org>/<repo-1> && git pull && \
  git worktree add ~/repos/<org>/tasks/task-1234-foo/<repo-1> -b task-1234-foo
cd ~/repos/<org>/<repo-2> && git pull && \
  git worktree add ~/repos/<org>/tasks/task-1234-foo/<repo-2> -b task-1234-foo
# …repeat per repo
```

It works, but the friction adds up: N manual commands per task; no single source of truth for "what does this task workspace consist of"; teardown is fiddly; cross-repo operations like "rebase each worktree onto main" require yet more manual loops.

`brunch` is a small CLI that:

- treats a directory of co-located git worktrees as one logical thing (a **workspace**);
- treats a directory of co-located workspaces as one logical thing (a **workspace set**);
- replaces the manual setup/teardown/sync work with single commands;
- is cheap to drive from an agent (Claude Code or similar) so workspace prep itself can be delegated.

The worktree property is central: everything stays linked to the canonical clone, commits cherry-pick cleanly across task workspaces, disk usage stays sane, and branch state is shared. `brunch` is a **cooperative semantic layer above `git worktree`** — never a replacement for it, never a parallel ledger of the same facts.

---

## 2. Core concepts

| Term | Meaning |
|---|---|
| **Canonical clone** | The primary on-disk clone of a repository, laid out at a deterministic path (see §4). Worktrees are added against this clone. brunch never clones; out-of-band tools do (`gh repo clone`, `ghq get`, a future GH-org catalogue tool). |
| **Workspace** | A directory containing one subdirectory per repo, each being a git worktree of the corresponding canonical clone. Marked by a `brunch.toml` manifest at its root. |
| **Workspace set** | A directory containing one or more workspaces as direct children. Marked by a `brunch-set.toml` manifest at its root. Members are defined by the filesystem — never enumerated in the manifest. |
| **Base** | For a workspace's per-repo entry: the branch that this worktree's branch was started from (or should be rebased onto). Recorded in the manifest; the basis for `brunch rebase`. |
| **Forge** | A git hosting platform (github.com, gitlab.com, a self-hosted gitlab, etc.). Used to construct canonical clone paths. github.com is the default and always available. |

### 2.1 Architectural stance

There are two layers of state, and they live in two different places:

1. **Git's `.git/worktrees/` directory inside each canonical clone** is the authoritative record of which worktrees exist for that repo, on what branches. It is durable, queryable (`git worktree list --porcelain`), and self-healing (`git worktree prune`).
2. **The on-disk workspace directory** (the `brunch.toml` plus the worktree subdirs) is the authoritative record of which worktrees belong together as one logical task workspace.

brunch does **not** maintain a third ledger that shadows either of these. There is no central registry of workspaces. There is no parallel record of "which worktrees exist." Everything brunch knows at runtime, it learns by reading these two layers. This is the most important architectural decision in the project, and many smaller decisions follow from it (see §11 and §12).

---

## 3. Filesystem conventions

### 3.1 Canonical clones — ghq-style layout

Canonical clones live under a configurable root, organised by forge / org / repo:

```
<root>/<forge_id>/<organisation>/<repo>
```

Default `root` is `~/repos/brunch` (overridable). The convention matches [ghq](https://github.com/x-motemen/ghq), `GOPATH/src/<importpath>` before Go modules, and the broad "import-path style" used by many tools. It is **the** standard convention in this neighbourhood, so adopting it puts brunch on familiar ground for anyone who has used those tools.

Example:

```
~/repos/brunch/
├── github.com/
│   ├── kybernetix/
│   │   ├── api/         <-- canonical clone of github.com/kybernetix/api
│   │   └── dashboard/
│   └── another-org/
│       └── …
└── gitlab.internal/
    └── platform/
        └── infra/
```

brunch never clones into this tree itself. It assumes well-formed clones already exist (placed there by `ghq get`, `gh repo clone`, or a future GH-org catalogue tool). When brunch needs to act on a repo, it computes the deterministic path and operates against it.

### 3.2 Workspace and workspace-set directories

Workspaces and sets are just directories. There is no special location they must live in; you can put them anywhere. In practice the author keeps them under `~/repos/<org>/tasks/`, but that is a personal choice and not enforced.

A workspace dir looks like:

```
task-1234-billing-flow/
├── brunch.toml           <-- workspace marker + manifest
├── api/                  <-- git worktree of kybernetix/api
└── dashboard/            <-- git worktree of kybernetix/dashboard
```

A workspace set looks like:

```
2026-Q2_billing-overhaul/
├── brunch-set.toml       <-- set marker
├── task-1234-billing-api/
│   ├── brunch.toml
│   ├── api/
│   └── dashboard/
├── task-1235-billing-internal-tools/
│   ├── brunch.toml
│   └── …
└── …
```

There is no global notion of "where workspaces are." brunch finds the one it should operate on via walk-up discovery from `cwd` (or from `-w <path>`); see §6.

---

## 4. Manifest schemas

### 4.1 `brunch.toml` (workspace manifest)

```toml
name = "task-1234-billing-flow"
description = "Add usage-based billing to API; surface in dashboard."

[[repo]]
repo   = "github.com/kybernetix/api"  # forge/org/repo; forge defaults to github.com
branch = "task-1234-billing-flow"
base   = "main"

[[repo]]
repo   = "kybernetix/dashboard"        # short form (forge inferred)
branch = "task-1234-billing-flow"
base   = "main"
```

Fields:

- `name` (string, required) — the workspace name. Conventionally the directory name; not technically required to match but normally does.
- `description` (string, optional) — free text, surfaced in `brunch status` and similar.
- `[[repo]]` (one or more) — each entry describes one repo and one worktree.
  - `repo` (string, required) — `<forge>/<org>/<repo>` or just `<org>/<repo>` (forge inferred from `default_forge` in tool config).
  - `branch` (string, required) — branch the worktree is on. Created if absent.
  - `base` (string, required) — what `branch` was started from / should be rebased onto. Usually `main`, but can be another local branch (including a sibling workspace's WIP branch, for stacking).

The schema is intentionally minimal. No commit pinning. No per-repo configuration knobs beyond what is strictly necessary. (See §12 for the rationale.)

### 4.2 `brunch-set.toml` (set manifest)

```toml
name = "2026-Q2_billing-overhaul"
description = "Billing redesign exploration — api/dashboard/marketing slice."
```

Fields:

- `name` (string, required)
- `description` (string, optional)

The set manifest **does not** enumerate member workspaces. Membership is defined by the filesystem: direct child directories that contain a `brunch.toml` are members. This is deliberate — see §11 (the registry decision).

Future fields (iteration 2+): set-level defaults inherited by `brunch init` of child workspaces, agent hints, etc.

### 4.3 Tool config — `~/.config/brunch/config.toml`

```toml
root          = "~/repos/brunch"
default_forge = "github.com"

[forges.github_com]
base_url = "https://github.com"

# Self-hosted example, only if needed:
# [forges.gitlab_internal]
# base_url = "https://gitlab.example.internal"
```

For the common case (only github.com), no config file is necessary; defaults apply. The XDG location is resolved via `platformdirs`.

---

## 5. Templates

### 5.1 Shape

A template is a partial workspace manifest, stored as a TOML file at:

```
~/.config/brunch/templates/<template_id>.toml
```

It has the same schema as `brunch.toml` minus `name`, plus the convention that any `[[repo]]` entry omitting `branch` will have it defaulted to the workspace name at materialisation time.

Example (`~/.config/brunch/templates/kybernetix-fullstack.toml`):

```toml
description = "Backend + dashboard, default for Acme fullstack tasks."

[[repo]]
repo = "kybernetix/api"
base = "main"

[[repo]]
repo = "kybernetix/dashboard"
base = "main"
```

### 5.2 Materialisation

`brunch init <name> -t <template_id>` reads the template, fills in `name = "<name>"`, defaults missing `branch` fields to `<name>`, writes `brunch.toml`, and proceeds with worktree creation as if the user had typed out the manifest by hand.

### 5.3 Out of scope for v1

No `brunch templates list/show/edit` commands. Templates are files in a known directory; `ls` is sufficient discovery for now. If the need for a richer template UX emerges, it can be added later without breaking changes.

### 5.4 Example templates

A handful of starter templates for a fictional Kybernetix product ship in
[`docs/examples/templates/`](examples/templates/) with installation
instructions and a per-template summary. They are documentation samples, not
auto-installed — copy any of them into `~/.config/brunch/templates/` to
activate.

---

## 6. CLI surface

### 6.1 Discovery rule (walk-up)

brunch determines its operating mode from the marker file it finds:

| Marker found (in cwd or walking up) | Mode |
|---|---|
| `brunch.toml` | **workspace mode** — operate on this workspace. |
| `brunch-set.toml` | **set mode** — fan operations out over child workspaces. |
| neither | error: "not inside a brunch workspace or set." |
| both at the same level | error: "ambiguous marker" (should not happen in practice). |

`-w <path>` overrides cwd-based discovery and points brunch at the directory directly.

### 6.2 Commands (v1)

| Command | Purpose |
|---|---|
| `brunch init <name> [-t <template>] [--set]` | Create a workspace (or, with `--set`, a workspace set) directory with an empty/templated manifest. |
| `brunch add <repo> [--branch X] [--base Y]` | Add a repo entry to the current workspace manifest; create its worktree against the canonical clone. |
| `brunch sync` | Converge on-disk worktrees with the manifest. Creates missing worktrees; warns on drift; never destructive. |
| `brunch status [--json]` | Summarised `git status` across all repos. JSON form is the canonical machine-readable format. |
| `brunch fetch` | Fan out `git fetch` across all repos. |
| `brunch pull` | Fan out `git pull` across all repos. |
| `brunch rebase [--onto B] [--continue-on-error] [--autostash] [--no-fetch]` | Per-repo `git fetch <base>` then `git rebase <base>` (or `<B>`). Stops on first conflict. |
| `brunch foreach <cmd>` | Run `<cmd>` in each repo subdir; passes through stdout/stderr unmodified. |
| `brunch rm [--force]` | Remove the workspace (or set) and prune worktrees from canonical clones. Refuses if anything is dirty unless `--force`, which archives first. |
| `brunch fsck [--json] [--fix]` | Diagnose health of the workspace (see §8.4). `--fix` performs only the safe automatic remediations. |

Universal flags:

- `--dry-run` — show what would happen without doing it. Honoured by every command that mutates state.
- `--json` — structured output (JSONL for record streams, JSON for single-shot results). Available for every read command.
- `-w/--workspace <path>` — operate from outside the dir.

### 6.3 Set-mode semantics

In set mode, the same commands fan out over child workspaces. Examples:

- `brunch status` from a set root aggregates status across all members.
- `brunch rebase` runs the per-workspace rebase semantics in each member.
- `brunch foreach <cmd>` runs `<cmd>` in every repo of every member workspace.
- `brunch fsck` checks each member.
- `brunch rm` removes the entire set (with the safety + archive flow).

A handful of commands do not apply at set level and error politely with a hint: `add`, `sync` (these belong to a specific workspace; cd in or use `-w`). `init` does apply — it creates either a workspace or a set depending on `--set`.

### 6.4 Binary aliases

The package installs two entry points pointing at the same Typer app:

- `brunch` — full name, used in docs.
- `br` — short alias, optimised for daily typing.

Both are first-class; either works anywhere.

---

## 7. Behavioural specifications

### 7.1 `brunch init`

- Workspace mode: creates `<name>/`, writes `brunch.toml` containing at least `name = "<name>"`. With `-t <template>` it materialises the template (see §5.2). Refuses if the target directory already exists.
- Set mode (`--set`): creates `<name>/` containing `brunch-set.toml` with `name = "<name>"`. Refuses if the target exists.

### 7.2 `brunch add`

- Resolves `<repo>` against the configured forges/root to compute the canonical clone path.
- **Pre-flight checks**: canonical clone exists and is a git repo; branch is not currently checked out in another worktree of that canonical clone (if it is, error with the conflicting path).
- Runs `git worktree add <workspace-dir>/<repo-shortname> [-b <branch>] [<base>]` against the canonical clone.
- Appends the corresponding `[[repo]]` entry to `brunch.toml`.

### 7.3 `brunch sync` — drift policy

The manifest is **intent**; the on-disk state is **reality**. `sync` only takes additive, non-destructive action.

| Situation | Behaviour |
|---|---|
| Manifest entry exists; worktree dir missing | Create the worktree (idempotent). |
| Worktree exists, on the manifest's branch | No-op. |
| Worktree exists, on a different branch | Warn; no action. |
| Worktree has uncommitted changes | Warn; no action. |
| Worktree dir present but not in manifest | Warn; no action. The user decides whether to `brunch add` or remove. |
| Branch already checked out in another worktree | Pre-flight error before any side effects. |

All warnings appear as structured records under `--json`.

### 7.4 `brunch rebase`

For each repo in the workspace (or each workspace in the set):

1. Unless `--no-fetch`: `git fetch <origin-tracking-remote-of-base> <base-shortname>`.
2. `git rebase <base>` (or `<--onto>` if supplied) on the worktree's current branch.
3. If `--autostash`: pass through to git.
4. If a rebase hits a conflict: stop immediately, report which repo, leave the rebase in progress, exit non-zero. With `--continue-on-error`: continue with the remaining repos and aggregate a report at the end.

`--onto <branch>` lets you rebase all worktrees onto a sibling task's WIP branch — the stacking case spelled out in the original handoff.

### 7.5 `brunch rm` and archiving

- **Default**: refuse if any repo has uncommitted changes, untracked-but-relevant files, or unpushed commits on branches that would be orphaned. Print exactly what is at risk and which `--force` is required.
- **With `--force`**: archive the entire workspace (or set) directory to `~/.local/share/brunch/archives/<name>-<UTC-timestamp>.tar.gz` **before** any destructive action, then remove worktrees via `git worktree remove`, run `git worktree prune` on each affected canonical, and delete the workspace dir.
- Branches are **not** deleted. They live on in the canonical clone and can be recreated as worktrees later. (Branch deletion is opt-in territory deferred to iteration 2.)
- `--dry-run` shows the full plan without acting.

The archive is a "fat" tarball of the workspace directory — simple, complete, slightly larger than necessary. A leaner format (manifest + per-repo `git bundle` of unpushed commits + uncommitted diffs) is a possible later refinement when archive size starts mattering.

#### Deletion safety contract

brunch only ever deletes things it knows it owns. The contract:

1. **Marker file.** `brunch.toml` is deleted (only when the workspace is otherwise empty).
2. **Manifest-declared worktrees.** Each `[[repo]]`'s subdir is removed via `git worktree remove` (with `--force` only when the user passed `--force`). Never `shutil.rmtree`.
3. **The workspace directory itself**, only when (1)+(2) above leave it empty.

Anything else under the workspace root — sibling directories, dotfiles, nested git repos, symlinks, files brunch never put there — is **preserved**. In that case the outcome is reported as `partial`: the workspace dir survives, `brunch.toml` is left alongside, and the preserved entries are listed in the rendered output (and in the `preserved` field of the JSON outcome). The user can then either review and remove manually, or `brunch sync`/`brunch rm` again later. `--force` does *not* override this contract; the archive captures the preserved content, so it's still recoverable if the user later decides to nuke the dir manually.

Additional safety guards: brunch refuses to operate on the filesystem root, the user's home directory, or any other absolute path with two or fewer components. If `--force` is set and archive creation fails (disk full, permission denied), the removal is aborted before any worktree is touched.

Reserved-name namespace: `.brunch/` is treated as brunch-owned so future state (e.g. lockfiles in iteration 3+) can be cleaned up automatically by `rm` without breaking the safety contract.

### 7.6 `brunch fsck`

Per workspace (recurses through set members in set mode):

- `brunch.toml` parses cleanly and matches the schema.
- Every `[[repo]]` resolves to an existing canonical clone that is a real git repo.
- Every `[[repo]]` has a corresponding worktree subdir under the workspace root.
- Each worktree is healthy (`git -C <worktree> rev-parse HEAD` succeeds; gitdir pointer intact).
- The worktree's current branch matches the manifest's (warning, non-fatal).
- The worktree's branch is not concurrently checked out in another worktree of the same canonical clone.
- The canonical clone has no dangling worktree refs (refs pointing at paths that no longer exist).
- No subdirectory under the workspace root looks like a worktree but is missing from the manifest.

Each issue is reported with a fix suggestion. Exit non-zero on any failure. `--fix` performs only the safe automatic remediations (e.g. `git worktree prune` on a canonical with dangling refs); it never deletes worktrees or branches, never resets state.

---

## 8. Agent-driveability

Three properties matter, and are treated as first-class:

1. **Structured output.** Every read command supports `--json`. Manifest-shaped pipelines use TOML; record streams (status, fsck results) use JSONL. Free-text commands (`foreach`) pass through git's stdout/stderr unmodified.
2. **Idempotence.** `init`, `add`, `sync` converge to the same state regardless of how many times they are run. `rebase` is naturally non-idempotent but explicit about its state.
3. **No interactive prompts in non-tty.** Every destructive operation has either a `--force` or a `--yes` switch. `--dry-run` exists everywhere. Exit codes are stable and documented.

This is what makes it realistic for an agent to be given permission to prepare a workspace for a new task without supervision.

---

## 9. Naming and ergonomics

The tool is called **brunch**, after the way a breakfast table is laid out before the diners arrive — a small mise-en-place that makes the work that follows easy. It also puns on "branch."

Daily ergonomics favour the short alias `br`. Both are registered as entry points; documentation uses `brunch` (clearer), shells use `br` (shorter).

There is a JavaScript build tool called Brunch. Since this is currently an internal tool with no immediate publishing plans, the collision is accepted. If public release is ever considered, a rename can be revisited; the v1 commitment is small.

---

## 10. Stack and tooling

| Concern | Choice | Why |
|---|---|---|
| Language | **Python 3.11+** | Velocity for design-discovery phase; mature ecosystem; agent-friendly. |
| CLI framework | **Typer** | Type-driven, plays well with Rich, low ceremony for our command count. |
| Terminal UI | **Rich** | Tables, colour, progress; first-class with Typer. |
| TOML read | **`tomllib`** (stdlib) | Built into 3.11+; no dependency cost. |
| TOML write | **`tomli-w`** | No stdlib equivalent yet. |
| Schema | **Pydantic v2** | Validation; JSON schema export usable by `--json` consumers. |
| OS paths | **`platformdirs`** | XDG on Linux; correct equivalents elsewhere. |
| Git invocation | **`subprocess`** (stdlib) | git's CLI is the contract; an extra abstraction layer adds risk without value. |
| Build/install | **uv** + **hatchling** | `uv tool install brunch` gives near-native UX; hatchling is the modern minimal build backend. |
| Tests | **pytest** | Real git in `tmp_path`; avoid mocking git. |
| Lint/format | **ruff** | One tool, fast. |
| Type-check | **mypy** | Strict on `src/`, lenient on `tests/`. |

The static-binary aesthetic of Rust or Go is appealing in the abstract but does not pay rent for a tool dominated by subprocess invocations and filesystem traversal. Python with `uv tool install` is effectively zero-friction to install for our audience. A port to Go is the natural escape hatch if distribution constraints ever change; Rust is also viable but its compile-time cost would slow iteration during the design-discovery phase we are still in.

---

## 11. Decisions log

A concise table of what was decided and where the reasoning lives.

| # | Decision | Where |
|---|---|---|
| D1 | Cooperative semantic layer over `git worktree`; no parallel ledger of worktree state. | §2.1, §12.1 |
| D2 | No central registry of workspaces; no `brunch list`. | §3.2, §12.2 |
| D3 | Walk-up discovery from cwd, modelled on git's own. | §6.1 |
| D4 | Workspace-set membership is filesystem-defined, not enumerated in the manifest. | §4.2, §12.3 |
| D5 | Canonical clones laid out ghq-style at `<root>/<forge>/<org>/<repo>`; brunch never clones. | §3.1, §12.4 |
| D6 | Manifest records intent (branches), never state (commits). No pinning in v1. | §4.1, §12.5 |
| D7 | `sync` is non-destructive; warns on drift, never resets. | §7.3 |
| D8 | `rm` defaults to refusal on dirty state; `--force` archives first to `~/.local/share/brunch/archives/`. | §7.5 |
| D9 | `rebase` is first-class (not `foreach git rebase`) and stops on first conflict by default. | §7.4, §12.6 |
| D10 | Templates are minimal: TOML files at `~/.config/brunch/templates/<id>.toml`, no management commands. | §5, §12.7 |
| D11 | `fsck` (not `doctor`) for the diagnostic command; tone matches git's neighbourhood. | §7.6 |
| D12 | Python + Typer for v1; Rust/Go a possible later port. | §10, §12.8 |
| D13 | No Linear integration in v1; convention-only branch naming. | §12.9 |
| D14 | Both `brunch` and `br` registered as entry points. | §6.4, §9 |

---

## 12. Alternatives considered

Each entry lists what else was on the table, why we chose what we chose, and what we would lose if we changed our mind later.

### 12.1 Maintaining brunch's own worktree ledger

**Alternative**: brunch keeps its own database of "which worktrees exist", possibly in `~/.config/brunch/`.

**Rejected because**: this would shadow the authoritative record git already maintains in `<canonical>/.git/worktrees/`. Any divergence between the two becomes a drift bug. Reading from git directly (via `git worktree list --porcelain`) is fast and unambiguous.

**Tradeoff accepted**: brunch must shell out to git for worktree state on each invocation that needs it. This is cheap; git is fast for this kind of query.

### 12.2 Central registry of workspaces

**Alternative**: a JSONL or sqlite registry at `~/.config/brunch/workspaces.jsonl` listing every known workspace, populated by `init`/`add` and consumed by `brunch list`.

**Rejected because**: a registry needs reconciliation. Users delete directories, move them, copy them, work outside the registered roots. Every one of those actions becomes a drift surface to handle. There is no actual user need for global enumeration of workspaces — the directory layout the user already maintains *is* the list.

**Tradeoff accepted**: there is no `brunch list` command in v1. If the need ever arises (it has not so far), it can be added as a glob over a configured roots list — without changing the source-of-truth story.

### 12.3 Set membership in the set manifest

**Alternative**: `brunch-set.toml` enumerates its member workspaces.

**Rejected because**: drift again. `mv`-ing a workspace into or out of a set dir should "just work"; an explicit member list breaks that. The filesystem is already a perfectly good index.

**Tradeoff accepted**: set membership is implicit. If a user wants to *exclude* a child dir from set operations, they currently cannot — they would need to move it out. This has not surfaced as a real need.

### 12.4 Letting brunch clone repos on demand

**Alternative**: `brunch add` can `git clone` the canonical if it is not yet on disk, into a configured location.

**Rejected because**: cloning is well-served by existing tools (`gh repo clone`, `ghq get`, the future GH-org catalogue tool). Putting it inside brunch couples it to forge auth, default-branch detection, etc. — domains we should not own.

**Tradeoff accepted**: a user who tries to `brunch add` a repo whose canonical clone does not exist gets an informative error pointing at the tools that *can* clone it. One extra step on first use of a given repo; zero ongoing cost.

### 12.5 Commit pinning in the manifest

**Alternative**: `[[repo]]` entries can optionally pin a commit SHA, and `sync` reconciles either by warning or by resetting.

**Rejected for v1 because**: in the workflows we actually have, branch tips already record what we care about. Pinning becomes immediately stale, or forces the manifest to be rewritten on every push. The use cases worth solving (faithful archive/restore, cross-repo reproducibility, time-travel debugging) are better served by **lockfiles** (porcelain), with `git checkout <sha>` as plumbing — a separate concept from the day-to-day manifest.

**Tradeoff accepted**: v1 has no built-in answer to "reproduce this workspace exactly as it was on Tuesday." For now: `git log` per repo, or recreate manually. Lockfile porcelain is iteration 3.

### 12.6 `rebase` as a `foreach` recipe

**Alternative**: skip a dedicated `brunch rebase` and let users do `brunch foreach -- git rebase <base>`.

**Rejected because**: rebasing needs the manifest's `base` field, sensible default fetching, conflict-handling policy, and structured reporting — none of which `foreach` can express. The first-class command is small (well under 100 LoC of orchestration) and unlocks `--onto` for the stacking case.

**Tradeoff accepted**: one more command to maintain.

### 12.7 Richer template UX

**Alternative**: `brunch templates list/show/copy/edit`, variable interpolation syntax, conditional sections, parameterised arguments.

**Rejected for v1 because**: the bare-minimum shape (a TOML file, default branch = workspace name) covers the main use cases we have. Richer UX risks designing-for-hypotheticals.

**Tradeoff accepted**: nothing visible. Templates are files; `ls ~/.config/brunch/templates/` is the discovery tool. Iteration 2 can layer commands on top without breaking the file shape.

### 12.8 Rust or Go from the start

**Alternative**: build in Rust (single static binary, strong types) or Go (single binary, fast compile, mature CLI ecosystem).

**Rejected for v1 because**: the differentiating cost of this project is design-discovery, not execution speed. Python keeps the iteration loop tight while the design is still settling. Distribution via `uv tool install` is effectively a single command for users — the static-binary advantage is real but small for this audience.

**Tradeoff accepted**: a Python runtime dependency for users. Mitigated by uv's `tool install` semantics, which create an isolated venv per tool and behave very close to a static binary in practice. If the constraint changes (public release, shipping to environments without Python), a port is the natural next step — but porting a known-good design is a different and easier problem than discovering it in a slower language.

### 12.9 First-class Linear integration

**Alternative**: `brunch init --linear PROJ-123` queries Linear, prefills name and description, fetches related context.

**Rejected for v1 because**: it couples a small generic tool to one specific issue tracker, with auth, secrets management, and API surface to maintain. The same outcome is available via a thin shell wrapper or future pluggable preprocessor.

**Tradeoff accepted**: a small amount of manual typing for `brunch init`. A preprocessor (`brunch-linear-init PROJ-123` emitting a manifest fragment piped into `brunch init --from-stdin`) is an obvious iteration-2 step that keeps Linear out of brunch's core.

### 12.10 Cobra/Click without Typer; or no framework

**Alternative**: write the CLI by hand or with a thinner framework.

**Rejected because**: Typer covers help text, parsing, completions, and type-driven argument parsing with very little ceremony. The cost is one dependency that is itself thin (it sits on top of Click).

### 12.11 `doctor` as the diagnostic command name

**Alternative**: keep the name `doctor` (cargo/brew flavour).

**Rejected because**: `fsck` lives in git's neighbourhood and signals "structured diagnostic with fix suggestions" more accurately. The tool is fundamentally about git state; the name should rhyme with git's vocabulary.

---

## 13. Deferred work

These items are explicitly out of scope for v1 but expected to land in iteration 2 or later.

### Iteration 2 — niceties on top of a working v1
- **`brunch gc`** — walks the canonical-clone tree and runs `git worktree prune` on each, cleaning up dangling refs from deleted workspaces. Useful but not blocking; a `find … | xargs git -C … worktree prune` one-liner covers it for now.
- **`brunch restore`** — natural inverse of `brunch rm --force`'s archive. Without it, the archive is mainly superstition. The pair is worth landing together.
- **Pipe semantics** — `brunch inspect` emitting manifest TOML, `brunch apply --from-stdin` consuming it. This is what makes "pipe several brunch commands together" real.
- **Set templates** — a template that materialises a set + N child workspaces in one command. Useful for shapeup-cycle prep.
- **Set-level defaults inherited by children** — `default_root`, `default_base`, etc. in `brunch-set.toml` flowing down into `brunch init` inside the set.
- **`--purge-branches` opt-in on `brunch rm`** — current default leaves branches in place; sometimes that is undesirable.

### Iteration 3 — depends on external work or further design

- **GH-org catalogue integration** — once the parallel catalogue tool exists, `brunch add --from-catalogue api` could resolve short names through it.
- **Linear preprocessor** — `brunch-linear-init PROJ-123` external command piped into `brunch init --from-stdin`.
- **Lockfile porcelain** — reproducible workspace checkouts (multiple lockfiles per workspace possible), built on `git checkout <sha>` plumbing.
- **`brunch repair`** — wrapper around `git worktree repair` if we discover it is run often enough to deserve a first-class command.

### Out of scope, possibly forever

- **Submodules** — punt; users manage them inside the worktree.
- **Concurrent brunch invocations** — rely on git's own locking; document the caveat in passing.
- **Cross-repo atomic commits** — not solved by brunch; commits remain independent across worktrees.

---

## 14. Open items

Things that are decided in principle but will need fine-tuning during implementation:

- **Error message conventions.** A single, scannable shape for every failure (what went wrong; what specifically to do about it; structured form under `--json`). Aim to land this early so all command implementations follow it.
- **JSON schema for `--json` outputs.** Pydantic models exist already; we should export a JSON schema and keep it stable from v1, since agents will rely on it.
- **Behaviour of `add` on an entry that already exists.** Two reasonable options (no-op if identical, error if different) — pick during M2.
- **Naming review** before any public release.

---

## 15. Milestones

The implementation proceeds in small, testable slices. Each milestone is roughly one focused sitting.

- **M0 — Skeleton.** `pyproject.toml`, package layout, Typer app with every v1 command stubbed, `uv tool install .` working, smoke test for `--version` and `--help`. *(Done.)*
- **M1 — Read-only foundation.** Manifest and config parsing, ghq-style path resolution, `brunch status`, `brunch fsck`. *(Done.)*
- **M2 — Workspace creation.** `init` (including `-t <template>` and `--set`), `add`, `sync` per the drift policy. After this milestone, brunch replaces the manual `git worktree add` workflow. *(Done.)*
- **M3 — Cross-repo ops.** `fetch`, `pull`, `rebase`, `foreach`. *(Done.)*
- **M4 — Safe teardown.** `rm` with the archive-on-force flow. *(Done.)*
- **M5 — Set mode.** Walk-up discovery extended to `brunch-set.toml`; set-aware fanout for the existing commands; `fsck` recursion; structured-output polish across the board. *(Done.)*

### Iteration 2 work landed so far

- **`brunch adopt`** (and the `brunch init --adopt` synonym) — retroactively bring an existing folder of worktrees under brunch. Iterates direct children that look like worktrees (`<sub>/.git` is a file), reads each gitdir pointer to find the canonical, reverse-resolves it against the configured `root` to recover `<forge>/<org>/<repo>`, reads each worktree's current branch, writes `brunch.toml` (defaulting `base` to `"main"` for every repo — inferring it from upstream tracking is unreliable enough to be a footgun, and editing the manifest is cheap), then runs `sync` + `fsck` to verify. Conservative on failure: any per-worktree error aborts before anything is written. Fails clearly if a worktree doesn't sit under the configured root. *(Done.)*

Iteration 2 and 3 follow as outlined in §13.
