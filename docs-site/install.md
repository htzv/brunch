# Install

This page is for anyone installing `br` on their own machine. When you are done,
`br --version` works from any directory.

You need [uv](https://docs.astral.sh/uv/), git, and Python 3.11 or newer.

## Install a release

```bash
uv tool install git+https://github.com/htzv/brunch@v0.1.0rc1
br --version
```

Replace `v0.1.0rc1` with the tag you want. The tags are listed at
<https://github.com/htzv/brunch/tags>. Without `@<tag>` you get the latest commit
on `main`, which may be ahead of the last release.

## Where it goes

uv puts `br` and `brunch` (the same command) in its tool bin directory. Print it
with `uv tool dir --bin`. On Linux it is `~/.local/bin` by default. If that
directory is not on your `PATH`, uv warns you when it installs. Run
`uv tool update-shell` to add it, then open a new shell.

## Install from a local checkout

```bash
uv tool install ./brunch               # copies the code as it is now
uv tool install --editable ./brunch    # links to the checkout instead
```

Use the editable form when you are developing brunch and want `br` to run your
working copy.

## Check what you have

```bash
br --version
uv tool list
cat "$(uv tool dir)/brunch/uv-receipt.toml"
```

The receipt shows where the install came from: a `git` line with the tag or
branch, or a `directory` line with the checkout it was copied from.

## Replace an old install

If `br --help` lacks commands you expect, such as `br agent` or `br drop`, your
install is older than the docs. A copy made from a directory never updates by
itself. Reinstall with `--force`, whatever the old install came from:

```bash
uv tool install --force git+https://github.com/htzv/brunch@v0.1.0rc1
```

## Uninstall

```bash
uv tool uninstall brunch
```
