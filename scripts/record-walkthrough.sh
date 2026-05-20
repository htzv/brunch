#!/usr/bin/env bash
# Re-record every asciinema cast embedded in the brunch walkthrough docs.
#
# This script:
#   1. Sets up an isolated demo environment (fake $HOME, fake canonical
#      clones, a fake `gh` and bare-repo `origin` so push/PR commands work
#      without network).
#   2. Installs the local brunch in editable mode against the demo env.
#   3. Records one `.cast` per tutorial step via `asciinema rec`.
#
# Re-running overwrites docs-site/assets/casts/*.cast in place.

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate the repo root from any cwd.
# ---------------------------------------------------------------------------
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CASTS_DIR="$REPO_ROOT/docs-site/assets/casts"
DEMO_TASK="${BRUNCH_DEMO_TASK:-task-1234-add-export}"

# ---------------------------------------------------------------------------
# Sanity checks.
# ---------------------------------------------------------------------------
for cmd in asciinema git uv; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "error: required command '$cmd' not found on PATH" >&2
    exit 1
  fi
done

# ---------------------------------------------------------------------------
# Isolated environment under $DEMO_ROOT — wiped and recreated on each run.
# ---------------------------------------------------------------------------
DEMO_ROOT="${BRUNCH_DEMO_ROOT:-/tmp/brunch-walkthrough}"
rm -rf "$DEMO_ROOT"
mkdir -p "$DEMO_ROOT"

export HOME="$DEMO_ROOT/home"
export XDG_CONFIG_HOME="$HOME/.config"
export XDG_DATA_HOME="$HOME/.local/share"
mkdir -p "$HOME" "$XDG_CONFIG_HOME" "$XDG_DATA_HOME"

# Configure brunch root to live under the demo home.
mkdir -p "$XDG_CONFIG_HOME/brunch/templates"
cat > "$XDG_CONFIG_HOME/brunch/config.toml" <<EOF
root          = "$HOME/repos/brunch"
default_forge = "github.com"
EOF

# Drop the acme-fullstack template.
cat > "$XDG_CONFIG_HOME/brunch/templates/acme-fullstack.toml" <<'EOF'
description = "Backend + frontend for typical acme fullstack tasks."

[[repo]]
repo = "acme/backend"

[[repo]]
repo = "acme/frontend"
EOF

# ---------------------------------------------------------------------------
# Fake canonical clones with a "remote" bare repo each, so `git push -u
# origin HEAD` actually works without touching real GitHub.
# ---------------------------------------------------------------------------
ACME_DIR="$HOME/repos/brunch/github.com/acme"
REMOTES_DIR="$DEMO_ROOT/remotes"
mkdir -p "$ACME_DIR" "$REMOTES_DIR"

for repo in backend frontend; do
  bare="$REMOTES_DIR/$repo.git"
  canonical="$ACME_DIR/$repo"
  git init --quiet --bare "$bare"
  git init --quiet -b main "$canonical"
  (
    cd "$canonical"
    git config user.name  "brunch-demo"
    git config user.email "demo@example.invalid"
    echo "# acme/$repo" > README.md
    git add README.md
    git -c user.name=brunch-demo -c user.email=demo@example.invalid commit -qm "initial commit"
    git remote add origin "$bare"
    git push -q -u origin main
  )
done

# ---------------------------------------------------------------------------
# Fake `gh` shim that prints a plausible PR URL for `gh pr create --fill`.
# ---------------------------------------------------------------------------
SHIM_DIR="$DEMO_ROOT/bin"
mkdir -p "$SHIM_DIR"
cat > "$SHIM_DIR/gh" <<'EOF'
#!/usr/bin/env bash
# Tutorial-only stub: just for `gh pr create --fill` recordings.
if [[ "$1" == "pr" && "$2" == "create" ]]; then
  shift 2
  base=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --base) base="$2"; shift 2;;
      --fill) shift;;
      *) shift;;
    esac
  done
  repo=$(basename "$(git rev-parse --show-toplevel)")
  branch=$(git rev-parse --abbrev-ref HEAD)
  num=$(( RANDOM % 200 + 1 ))
  echo "Creating pull request for $branch into ${base:-main} in acme/$repo"
  echo "https://github.com/acme/$repo/pull/$num"
  exit 0
fi
exec /usr/bin/gh "$@"
EOF
chmod +x "$SHIM_DIR/gh"
export PATH="$SHIM_DIR:$PATH"

# ---------------------------------------------------------------------------
# Install brunch (editable) into a venv so `brunch` is on PATH.
# ---------------------------------------------------------------------------
VENV_DIR="$DEMO_ROOT/venv"
(
  cd "$REPO_ROOT"
  uv venv --quiet "$VENV_DIR"
  uv pip install --quiet --python "$VENV_DIR/bin/python" -e .
)
export PATH="$VENV_DIR/bin:$PATH"

# ---------------------------------------------------------------------------
# Recording helpers.
# ---------------------------------------------------------------------------
mkdir -p "$CASTS_DIR"

# Each step function defines the exact prompt + commands. We feed them into
# asciinema via stdin so they appear interactively typed.
record() {
  local name="$1"
  local commands="$2"
  local cast="$CASTS_DIR/$name.cast"
  echo "→ recording $name ..."
  rm -f "$cast"
  # `asciinema rec -c "bash -c '<commands>'"` runs the whole block at once;
  # we instead feed commands line-by-line so the cast shows realistic pacing.
  PS1='\W \$ ' \
  asciinema rec \
    --overwrite \
    --idle-time-limit 1 \
    --title "brunch walkthrough — $name" \
    --command "bash --noprofile --norc -i" \
    "$cast" <<< "$commands
exit
"
}

# ---------------------------------------------------------------------------
# Steps. Each one is a small bash heredoc that drives the demo session.
# ---------------------------------------------------------------------------
TASKS_DIR="$HOME/repos/acme/tasks"
mkdir -p "$TASKS_DIR"

step_00_setup() {
  record 00-setup "$(cat <<EOF
brunch --version
cat \$XDG_CONFIG_HOME/brunch/config.toml
ls \$HOME/repos/brunch/github.com/acme
cat \$XDG_CONFIG_HOME/brunch/templates/acme-fullstack.toml
EOF
)"
}

step_01_create() {
  record 01-create "$(cat <<EOF
cd $TASKS_DIR
brunch init $DEMO_TASK -t acme-fullstack
ls $TASKS_DIR/$DEMO_TASK
cat $TASKS_DIR/$DEMO_TASK/brunch.toml
EOF
)"
}

step_02_inspect() {
  record 02-inspect "$(cat <<EOF
cd $TASKS_DIR/$DEMO_TASK
brunch status
brunch fsck
EOF
)"
}

step_03_claude_code() {
  record 03-claude-code "$(cat <<EOF
cd $TASKS_DIR/$DEMO_TASK
echo "(starting Claude Code in workspace root — agent would see both repos as siblings)"
echo "claude  # — interactive; mocked here"
ls
EOF
)"
}

step_04_verify() {
  # Drop a trivial passing pytest into each backend/frontend worktree so
  # the cast shows real green output.
  for d in $TASKS_DIR/$DEMO_TASK/backend $TASKS_DIR/$DEMO_TASK/frontend; do
    mkdir -p "$d/tests"
    cat > "$d/tests/test_demo.py" <<'PY'
def test_demo(): assert True
PY
  done
  record 04-verify "$(cat <<EOF
cd $TASKS_DIR/$DEMO_TASK
brunch foreach -- python -m pytest -q
brunch status
EOF
)"
}

step_05_commit() {
  record 05-commit "$(cat <<EOF
cd $TASKS_DIR/$DEMO_TASK
brunch foreach -- git add -A
brunch foreach -- git status --short
( cd backend  && git commit -q -m "feat: add /api/v1/users/export CSV endpoint" )
( cd frontend && git commit -q -m "feat(users): add 'Download CSV' button" )
brunch foreach -- git log --oneline -2
EOF
)"
}

step_06_push() {
  # Wire each worktree's origin to its bare remote so push actually works.
  for repo in backend frontend; do
    git -C "$TASKS_DIR/$DEMO_TASK/$repo" remote add origin "$REMOTES_DIR/$repo.git" 2>/dev/null || true
  done
  record 06-push "$(cat <<EOF
cd $TASKS_DIR/$DEMO_TASK
brunch foreach -- git push -u origin HEAD
brunch status
EOF
)"
}

step_07_pr() {
  record 07-pr "$(cat <<EOF
cd $TASKS_DIR/$DEMO_TASK
brunch foreach -- gh pr create --fill --base main
EOF
)"
}

step_08_teardown() {
  record 08-teardown "$(cat <<EOF
cd $TASKS_DIR
brunch rm -w $DEMO_TASK
ls $TASKS_DIR
EOF
)"
}

# ---------------------------------------------------------------------------
# Run all steps in order.
# ---------------------------------------------------------------------------
step_00_setup
step_01_create
step_02_inspect
step_03_claude_code
step_04_verify
step_05_commit
step_06_push
step_07_pr
step_08_teardown

echo ""
echo "All casts re-recorded into $CASTS_DIR/"
ls -lh "$CASTS_DIR"/*.cast
