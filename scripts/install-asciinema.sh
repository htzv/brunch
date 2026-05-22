#!/usr/bin/env bash
# Fetch a pinned asciinema 3.x binary from the upstream GitHub release page
# and drop it under `tools/asciinema` in this repo. The recording script
# (scripts/record-walkthrough.sh) prepends `tools/` to PATH automatically.
#
# Why this script exists:
# - asciinema 3.x is a Rust rewrite; upstream stopped publishing to PyPI at
#   v2.4.0, so `uv tool install asciinema` won't get us a usable version.
# - Debian/Ubuntu's `asciinema` package is still 2.x as of 2026.
# - This script needs no sudo, no system package manager, no `~/.local/bin`
#   PATH-juggling — the binary lives in the repo's `tools/` dir, gitignored.
#
# Override the version with: `ASCIINEMA_VERSION=3.2.0 ./scripts/install-asciinema.sh`
# Override the variant with: `ASCIINEMA_LINUX_VARIANT=musl` (defaults to `gnu`).

set -euo pipefail

VERSION="${ASCIINEMA_VERSION:-3.2.0}"
LINUX_VARIANT="${ASCIINEMA_LINUX_VARIANT:-gnu}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLS_DIR="$REPO_ROOT/tools"
TARGET="$TOOLS_DIR/asciinema"

# ---------------------------------------------------------------------------
# Detect platform.
# ---------------------------------------------------------------------------
os=$(uname -s | tr '[:upper:]' '[:lower:]')
arch=$(uname -m)

case "$arch" in
  aarch64|arm64) arch=aarch64 ;;
  x86_64|amd64)  arch=x86_64 ;;
  *)
    echo "error: unsupported CPU architecture: $arch" >&2
    exit 1
    ;;
esac

case "$os" in
  linux)
    asset="asciinema-${arch}-unknown-linux-${LINUX_VARIANT}"
    ;;
  darwin)
    asset="asciinema-${arch}-apple-darwin"
    ;;
  *)
    echo "error: unsupported OS: $os" >&2
    exit 1
    ;;
esac

url="https://github.com/asciinema/asciinema/releases/download/v${VERSION}/${asset}"

# ---------------------------------------------------------------------------
# Skip if already installed at the desired version.
# ---------------------------------------------------------------------------
if [[ -x "$TARGET" ]]; then
  installed=$("$TARGET" --version 2>&1 | awk 'NR==1 { print $NF }' || true)
  if [[ "$installed" == "$VERSION" ]]; then
    echo "asciinema $VERSION already installed at $TARGET; nothing to do."
    exit 0
  fi
  echo "replacing existing $TARGET (was $installed, installing $VERSION)"
fi

# ---------------------------------------------------------------------------
# Download.
# ---------------------------------------------------------------------------
mkdir -p "$TOOLS_DIR"

if ! command -v curl >/dev/null 2>&1; then
  echo "error: \`curl\` not found on PATH" >&2
  exit 1
fi

echo "downloading $asset from $url ..."
curl --fail --location --silent --show-error \
  --output "$TARGET" \
  "$url"
chmod +x "$TARGET"

# ---------------------------------------------------------------------------
# Verify.
# ---------------------------------------------------------------------------
installed=$("$TARGET" --version 2>&1 | awk 'NR==1 { print $NF }' || true)
if [[ "$installed" != "$VERSION" ]]; then
  echo "warning: installed binary reports version '$installed' (expected '$VERSION')" >&2
fi

cat <<EOM

  installed asciinema $installed → $TARGET

next steps:
  ./scripts/record-walkthrough.sh    # picks up tools/asciinema via PATH

EOM
