#!/usr/bin/env bash
# Run the test suite on every supported Python version, listed in
# scripts/python-versions.txt (which CI reads too). Runs all versions, then
# fails if any failed.
set -uo pipefail

cd "$(dirname "$0")/.."
failed=()
while read -r version; do
  [[ -z "$version" ]] && continue
  echo "=== Python ${version}"
  scripts/run-tests.sh "$version" || failed+=("$version")
done < scripts/python-versions.txt

if ((${#failed[@]})); then
  echo "FAILED on: ${failed[*]}" >&2
  exit 1
fi
