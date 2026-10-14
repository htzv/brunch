# brunch: notes for coding agents

This file is for agents working **on** brunch and agents using `br` for someone.
It does not repeat command syntax. `br --help` and `br <command> --help` are the
reference for flags and behaviour. Read them before you run a command you have not
used in this session.

`br` creates and deletes git worktrees. A wrong call can discard work that has not
been pushed, so the rules below are about not guessing.

## Rules

1. **Verify, never assume.** Base every analysis, recommendation and decision on
   code you have read or output you have seen. For anything non-trivial, write a
   small throwaway script that checks the claim, and run it. Do not state a value,
   a path or a command's behaviour from memory.
2. **Keep throwaway scripts out of git.** Put them in `_scripts/` at the root of
   the task's br workspace, next to the worktree and so outside the repository.
   For a check that spans several tasks, use `_scripts/` in the parent workspace.
3. **Preview before you delete.** Run `br rm`, `br drop` and `br agent rm --purge`
   with `--dry-run` first, and read the result.
4. **Do not use `--force` to get past a refusal.** A refusal means the worktree has
   uncommitted, untracked or unpushed work. Report it and ask.
5. **Do not enable experimental features on your own.** `--enable-experimental`
   exists so that a person opts in on purpose.
6. **Stop on the first surprise** and say what you saw, with the command output.

## Working on brunch

- **Use the branch's own `br`.** In a worktree you are changing, run
  `uv run br ...` from that worktree, so you test the code you are editing and not
  an older install. Exceptions: that branch's `br` is broken or half-refactored
  (use another worktree's, or the home-wide `br`), and plain git operations.
- **One task, one br workspace.** Each task gets its own workspace holding one
  worktree of this repo. Keep each pull request small and self-contained.
- **Checks before a PR:**

  ```bash
  uv run ruff check . && uv run ruff format --check . && uv run mypy src
  uv run pytest --cov=brunch      # CI fails below 85% coverage
  uv run mkdocs build --strict    # when docs changed
  ```

- **Tests use real git** in temporary directories. Do not mock git.

## Code guidelines

These apply to new and changed code. Do not refactor unrelated code in the same
pull request.

- **Small, focused files.** One file covers one aspect of the tool. When files
  share a concern, group them in a directory. Around 200 to 250 lines of code
  (not counting comments and docstrings) is the point where a file is too large.
  This is a guide, not a hard limit, but going over needs a reason.
- **Make the code say it.** Choose names that explain intent. When a block is hard
  to read, split it into small functions and build the algorithm from them.
- **Comment only what the code cannot say.** Do not narrate what the code does. Do
  not record history ("we used to...") or argue for a decision. Names, test names
  and test assertions carry the intent.
- **No magic numbers.** Give every number a named constant
  (`SCREAMING_SNAKE_CASE`).
- **Use types for correctness and for reading.** Prefer enums, `Literal`, frozen
  sets and frozen models over bare strings and mutable collections whenever a
  value comes from a fixed set.
- **Make illegal states impossible to represent**, as long as it stays simple. If
  two fields only make sense together, model them as one type. Do not build
  machinery for a state that cannot happen.

## Versions and releases

There is no full release process yet. These rules cover how a pull request
handles the version.

The version is the `version` field in `pyproject.toml`, and nothing else defines
it. `br --version` reads it from the installed package. After you change it, run
`uv lock` and commit `uv.lock` in the same commit.

- **Ask before you bump.** When you prepare a pull request, ask the person you
  are working with whether it should bump the version. Recommend a size:
  - **major** for a breaking change: a schema change, a changed default, or a
    removed or renamed command or flag. Anything that makes existing files or
    habits stop working;
  - **minor** for a backwards-compatible addition, such as a new command or flag;
  - **patch** for a bug fix, a docs-only change, or an internal change that does
    not affect user-facing behaviour or contracts.

  While the major version is 0, a breaking change bumps the minor instead, and the
  major version stays 0 until the person decides the basics are stable.
- **Release candidates for pieces of a larger change.** Some changes are small
  only because of the size limit on pull requests, and belong to a larger piece of
  work. They do not deserve their own patch number. Recommend a release candidate
  of the next version instead, for example `0.1.3rc5`. The final pull request of
  the set drops the suffix (`0.1.3`).
- **Bump in its own commit**, and only when the person says yes.
- **Tag releases.** A release is a git tag on the commit that bumped the version:
  `v0.1.3`, or `v0.1.3rc5` for a release candidate. After the bump is merged,
  propose the tag. Create and push it once the person agrees.

## Writing docs and help text

This covers READMEs, the docs site, `--help` text and docstrings. Write so that a
tired colleague who has never used brunch can follow it.

- **Start with who it is for and what they can do after reading.**
- **Short sentences, concrete words, active voice.** One idea per sentence. Say
  what a command does, and what it does not touch.
- **Say it plainly.** Avoid metaphors and marketing words: "first-class",
  "cooperative semantic layer", "ledger" (for anything but money), "earns its
  keep", "unlocks", "spiritual successor", "seamless", "leverage".
- **Keep design history out of user docs.** Why a decision was made belongs in the
  design memo, not in the README or `--help`.
- **Use bold sparingly** and do not stack em-dashes. If a sentence needs three
  asides, split it.
- **Examples use fictional repos**, such as `github.com/example.com/backend` and
  `frontend`.
- **Check every claim against the code or by running the command.** The rule
  "verify, never assume" applies to docs too.
- **Quoted text is exempt.** An excerpt set as a quote, such as the author's own
  description of brunch in the README, keeps its original wording. These rules do
  not apply inside it.

Examples taken from the current docs:

| Before | After |
|---|---|
| This is the moment the workspace earns its keep. Because both repos sit under a single directory, an agent that can read the filesystem has the full cross-repo picture in one shot. | Both repos sit under one directory, so an agent that can read files sees both without you copying context between them. |
| Brunch sits on top of `git worktree` as a cooperative semantic layer. It never replaces git's own state, just orchestrates around it. | Brunch runs `git worktree` for you. It keeps no record of its own about which worktrees exist. It reads that from git and from `brunch.toml`. |
| Both `brunch` and the short alias `br` are first-class. | `brunch` and `br` are the same command. |
| brunch does **not** maintain a third ledger that shadows either of these. This is the most important architectural decision in the project. | Brunch keeps no separate list of worktrees. Git records which worktrees exist, and the workspace directory records which ones belong together. Brunch reads both each time it runs. |

## Using `br` non-interactively

- `--json` prints machine-readable output on most commands (`br agent list` and
  `br agent sync` among the `agent` commands). Prefer it when you
  need to parse the result.
- `--dry-run` shows what would happen and changes nothing. It is available on
  `init`, `adopt`, `add`, `sync`, `fetch`, `pull`, `rebase`, `foreach`, `rm`,
  `drop` and `agent rm`. `status` and `fsck` have none.
- `-w/--workspace <path>` runs a command against a workspace without changing
  directory. Without it, `br` looks for `brunch.toml` upward from the current
  directory.
- `br rm` and `br drop` refuse when a worktree has uncommitted, untracked or
  unpushed work. `--force` overrides this, and `br rm --force` archives the
  workspace first.
- `br agent resume` needs a selector when there is more than one conversation. It
  cannot show a picker without a terminal.

Exit codes:

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Refused or failed (for example, `rm` or `drop` found work at risk) |
| 2 | Usage error, or an experimental feature used without opting in |
| 3 | No workspace found |
| 4 | Invalid `brunch.toml` |
| 5 | Invalid tool config |
| 6 | Invalid repo spec |
| 7 | A git command failed |
| 8 | Template error |
| 9 | Target already exists |
| 10 | Branch is already checked out elsewhere |
| 11 | Repo is already in the workspace |
| 12 | Agent error |
