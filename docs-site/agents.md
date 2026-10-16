# Use brunch from a coding agent

This page is for anyone who runs a coding agent (Claude Code, OpenCode) inside a
brunch workspace and wants it to use `br` without surprises. When you are done,
you have a short block of instructions to give the agent, and you know what each
line of it is for.

## The block

Paste this into the agent's instructions (`AGENTS.md`, `CLAUDE.md`) or into your
first prompt:

```text
This directory is a brunch workspace: one git worktree per repo, for one task,
managed with the `br` command. Before you use `br`, run `br --help`, and
`br <command> --help` for each command you plan to run. Do not rely on memory for
flags or behaviour.

You may run without asking: `br status`, `br fsck`, `br fetch`, `br agent list`,
any command with `--dry-run`, and `br init`, `br add` and `br sync`, which create
worktrees and delete nothing.

Ask me first, and show the `--dry-run` output: `br rm`, `br drop`, `br pull`,
`br rebase`, `br foreach` and `br agent rm`.

Never use `--force` or `--enable-experimental` to get past a refusal. A refusal
means a worktree has uncommitted, untracked or unpushed work. Report it and stop.
Do not add `--no-fetch` to get past a network error unless I say we are offline.

Use `--json` when you need to parse the output, and `-w <path>` to run a command
against a workspace without changing directory. If anything surprises you, stop
and show me the command and its output.
```

## What each part is for

- **Run `--help` first.** The help text is the reference for flags and behaviour,
  and it is kept in step with the code. An agent that guesses a flag can delete or
  rewrite things.
- **The commands it may run alone** only read, or only add. `br add`, `br sync` and
  `br init -t` fetch the repo's remote first, so they need network access.
- **The commands it asks about** change or remove something. `br rm` and `br drop`
  remove worktrees, `br pull` and `br rebase` change branches, and `br foreach`
  runs any command you give it in every repo. `--dry-run` shows the plan without
  doing it.
- **`--force`.** `br rm` and `br drop` refuse when a worktree has uncommitted,
  untracked or unpushed work. `--force` overrides that. Whether to discard work is
  your decision, not the agent's. Branches stay in the cloned repo after `br rm`, so
  committed work is not lost by removing a worktree, but uncommitted work is.
- **`--no-fetch`.** `br add` stops when the fetch fails, so it never starts a
  branch from stale refs. `--no-fetch` skips the fetch. That is right when you are
  offline, and wrong as a way around an error nobody has read.
- **Exit codes.** `0` is success and `1` is a refusal. The other codes are listed
  in `br --help`. An agent can act on the code.

## Try it

Ask the agent to run `br status` and `br rm --dry-run` and tell you what it sees.
If it reads `br rm --help` first, the block is working.

See also [AGENTS.md](https://github.com/htzv/brunch/blob/main/AGENTS.md), which is
written for agents that work on brunch itself.
