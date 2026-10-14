# Update

This page is for anyone who already has `br` installed and wants a newer version.
The right command depends on how you installed it, so check that first.

## Find out how you installed it

```bash
br --version
cat "$(uv tool dir)/brunch/uv-receipt.toml"
```

The `requirements` line in the receipt says where the install came from. A `git`
URL ending in `?rev=<tag>` is pinned to a tag. A `git` URL with no `rev` follows
the default branch. A `directory` line is a copy of a local checkout.

## Installed from a tag

A tagged install is pinned, so `uv tool upgrade brunch` reports "Nothing to
upgrade". Install the new tag instead:

```bash
uv tool install --force git+https://github.com/htzv/brunch@<new-tag>
```

List the tags with `git ls-remote --tags https://github.com/htzv/brunch`, or look
at <https://github.com/htzv/brunch/tags>.

## Installed without a tag

This install follows the default branch:

```bash
uv tool upgrade brunch
```

If there is a newer commit, uv reinstalls and prints the old and new versions.

## Installed from a local directory

`uv tool upgrade brunch` rebuilds from whatever is in that directory at the
moment. It does not update the directory. Update the checkout first, then
upgrade:

```bash
git -C <path-to-checkout> pull
uv tool upgrade brunch
```

An editable install runs the checkout as it is, so only the `git pull` is needed.

To stop depending on a checkout, switch to GitHub:

```bash
uv tool install --force git+https://github.com/htzv/brunch@<tag>
```

## Check the result

```bash
br --version
```
