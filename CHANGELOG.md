# Changelog

All notable changes to brunch are listed here, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions are git tags
(`v0.1.0rc2`); while the major version is 0, a breaking change bumps the minor
version. Entries refer to pull requests in
[htzv/brunch](https://github.com/htzv/brunch/pulls).

## [Unreleased]

### Added

- `br add` fetches the repo's remote first and starts the new branch from its
  current tip (`origin/main`) instead of a stale local `main`. The new branch does
  not track the remote branch. `--remote`/`-r` picks the remote (otherwise git's
  `checkout.defaultRemote`, the only remote, or `origin`), and `--no-fetch` works
  offline. The outcome and `--json` report `remote`, `start_point` and `fetched`.
  (#18, #19, #21)
- `br rm` and `br drop` recognise work that was already rebase-merged or
  squash-merged into the base branch, no longer refuse it, and say why
  (`merged` in `--json`). (#23, #26)
- `br rm` and `br drop` fetch and prune every remote before judging, also on
  `--dry-run`. A failed fetch is a warning (`fetch_warnings`), not an error, and
  `--no-fetch` skips the attempt. (#25)
- `br rm --dry-run` previews which repos it will remove from `brunch.toml`
  (`manifest_entries_dropped`). (#24)

### Changed

- **Breaking:** `br add` refuses when the branch already exists in the cloned
  repo, as `git checkout -b` does, instead of silently ignoring `--base`. Delete
  the leftover branch or pick another `--branch`. `br sync` still checks out an
  existing branch. (#20)
- `br rm` and `br drop` judge "unpushed" the way git does: commits that no remote
  branch contains. A branch updated with `git pull origin <branch>` is no longer
  refused for having no upstream. (#25)
- When `br rm` keeps the workspace directory, `brunch.toml` keeps only the repos
  whose removal failed. Before, it still listed repos whose worktrees were gone, so
  `br status` showed them as missing and `br sync` recreated them. (#24)

### Fixed

- A branch whose remote branch had been deleted could hide unpushed commits from
  `br rm` and `br drop`, because git omits the ahead count once the upstream is
  gone. (#25)
- `br rm` deleted `brunch.toml` when a worktree could not be removed, and its dry
  run said the workspace would be removed when the real run keeps it. (#24)

## [0.1.0rc2] - 2026-10-14

### Added

- Both manifests (`brunch.toml`, `brunch-set.toml`) carry a `schema_version`. (#12)
- Install and update pages. (#10, #11)
- Python 3.14 and 3.15 are tested in CI. (#13)

### Changed

- **Breaking, one time:** builds before 0.1.0rc2, including rc1, reject manifests
  written by rc2 or later, with an "extra inputs" error about `schema_version`.
  Update brunch on every machine that shares workspaces. (#12)
- A manifest written by a newer brunch is rejected with a message that says so,
  and links to the update page. Other validation errors name the file and the key,
  one per line. (#14)
- Error hints link to the published documentation instead of a file that only
  exists in the repository. (#15)

## [0.1.0rc1] - 2026-10-14

First release candidate.

### Added

- Commands: `init`, `adopt`, `add`, `sync`, `status`, `fetch`, `pull`, `rebase`,
  `foreach`, `rm`, `drop`, `fsck` and `agent`, for task workspaces of git worktrees
  (one directory per task, one worktree per repo) and sets of workspaces. (#1)
- `br drop` removes one repo's worktree and its `brunch.toml` entry. (#1)
- `br agent` keeps a registry of coding-agent conversations per workspace. (#1)
- `br <command> --help` is complete for every command, with an example. (#7, #8)
- The version is read from the installed package, so `br --version` is accurate. (#9)

[Unreleased]: https://github.com/htzv/brunch/compare/v0.1.0rc2...HEAD
[0.1.0rc2]: https://github.com/htzv/brunch/compare/v0.1.0rc1...v0.1.0rc2
[0.1.0rc1]: https://github.com/htzv/brunch/tree/v0.1.0rc1
