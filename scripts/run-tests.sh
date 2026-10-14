#!/usr/bin/env bash
# Run the test suite the way CI does: coverage gate, and GITHUB_ACTIONS=true so
# CI-only behaviour (such as Typer's coloured output) shows up locally.
#
# Usage: scripts/run-tests.sh [python-version]
#
# With a version, the suite runs in its own venv (.venv-<version>), so switching
# versions never rebuilds .venv. Without one, it uses .venv.
set -euo pipefail

version="${1:-}"
export GITHUB_ACTIONS=true

if [[ -n "$version" ]]; then
  export UV_PROJECT_ENVIRONMENT=".venv-${version}"
  uv run --python "$version" --extra dev pytest --cov=brunch --cov-report=term-missing
else
  uv run --extra dev pytest --cov=brunch --cov-report=term-missing
fi
