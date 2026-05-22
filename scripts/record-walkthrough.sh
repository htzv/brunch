#!/usr/bin/env bash
# Re-record every asciinema cast embedded in the brunch walkthrough docs.
#
# Three things this script gets right that a naive `asciinema rec -c` doesn't:
#
# 1. **Typewriter pacing.** Commands are printed character-by-character via a
#    `type_cmd` bash helper running inside the recorded session, with explicit
#    sleeps between keystrokes. Tunable via BRUNCH_TYPE_CPS (default 22 chars
#    per second, ~45 ms / char) and BRUNCH_POST_LINE_PAUSE (default 0.8s after
#    each command). Without this, casts show output at network speed and are
#    illegible.
#
# 2. **Fixed terminal size.** Every cast is recorded at exactly 80×40 via
#    asciinema's `--cols`/`--rows` flags, regardless of the host terminal
#    size. Requires asciinema 3.0 or later.
#
# 3. **No pagers.** GIT_PAGER and PAGER are forced to `cat` inside the
#    recorded session so `git log` (and any other paging tool) doesn't pop a
#    `less` UI into the cast.
#
# Re-running overwrites docs-site/assets/casts/*.cast in place.

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate the repo root from any cwd.
# ---------------------------------------------------------------------------
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CASTS_DIR="$REPO_ROOT/docs-site/assets/casts"
DEMO_TASK="${BRUNCH_DEMO_TASK:-task-1234-add-export}"

# Prefer a project-local asciinema binary if one has been dropped under
# tools/ by `./scripts/install-asciinema.sh`. Lets the recording flow stay
# decoupled from whatever stale asciinema is on the system PATH.
if [[ -x "$REPO_ROOT/tools/asciinema" ]]; then
  export PATH="$REPO_ROOT/tools:$PATH"
fi

# ---------------------------------------------------------------------------
# Tunable pacing (also overridable per-step; see helpers below).
# ---------------------------------------------------------------------------
TYPE_CPS="${BRUNCH_TYPE_CPS:-22}"
POST_LINE_PAUSE="${BRUNCH_POST_LINE_PAUSE:-0.8}"
IDLE_TIME_LIMIT="${BRUNCH_IDLE_TIME_LIMIT:-3}"
CAST_COLS="${BRUNCH_CAST_COLS:-80}"
CAST_ROWS="${BRUNCH_CAST_ROWS:-40}"

# ---------------------------------------------------------------------------
# Sanity checks.
# ---------------------------------------------------------------------------
for cmd in asciinema git uv awk; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "error: required command '$cmd' not found on PATH" >&2
    exit 1
  fi
done

# asciinema 3+ is required for --cols / --rows.
ASCIINEMA_VERSION=$(asciinema --version 2>&1 | awk 'NR==1 { print $2 }')
ASCIINEMA_MAJOR=$(printf '%s\n' "$ASCIINEMA_VERSION" | cut -d. -f1)
if [[ -z "$ASCIINEMA_MAJOR" || "$ASCIINEMA_MAJOR" -lt 3 ]]; then
  cat >&2 <<EOM
error: asciinema ${ASCIINEMA_VERSION:-(unknown)} detected; this script needs
3.0 or later for fixed terminal sizing via --cols/--rows.

Debian/Ubuntu still ship 2.x; install a newer version with one of:

  uv tool install asciinema
  pipx install --force asciinema
  pip install --user asciinema

EOM
  exit 1
fi

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
if [[ "${1:-}" == "pr" && "${2:-}" == "create" ]]; then
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
# Install brunch (editable) into a venv so `brunch` is on PATH inside the
# recorded session.
# ---------------------------------------------------------------------------
VENV_DIR="$DEMO_ROOT/venv"
(
  cd "$REPO_ROOT"
  uv venv --quiet "$VENV_DIR"
  uv pip install --quiet --python "$VENV_DIR/bin/python" -e .
)
export PATH="$VENV_DIR/bin:$PATH"

# ---------------------------------------------------------------------------
# Demo helpers — written once, sourced by each recorded session.
#
# `type_cmd '<cmd>'` prints the command character-by-character at human
# typing speed, then executes it.
#
# `demo_say '<note>'` prints a slow narrative comment.
#
# `demo_pause [seconds]` is a deliberate beat between actions.
# ---------------------------------------------------------------------------
HELPERS_FILE="$DEMO_ROOT/demo-helpers.sh"
cat > "$HELPERS_FILE" <<'HELPERS'
# Hide the heredoc-fed lines themselves; type_cmd does its own display.
stty -echo 2>/dev/null || true
# Pretend the tty is 80×40 so any program that asks ioctl(TIOCGWINSZ) gets
# a consistent answer (asciinema's --cols/--rows already sets this on the
# pty, but stty here belt-and-suspenders against shells that override it).
stty cols ${BRUNCH_CAST_COLS:-80} rows ${BRUNCH_CAST_ROWS:-40} 2>/dev/null || true

# No pagers: keep git log etc. from popping a less UI mid-cast.
export GIT_PAGER=cat
export PAGER=cat

# Force colour where the player can render it.
export FORCE_COLOR=1
export CLICOLOR_FORCE=1

: "${BRUNCH_TYPE_CPS:=22}"
: "${BRUNCH_POST_LINE_PAUSE:=0.8}"
: "${BRUNCH_PROMPT_COLOR:=32}"

type_cmd() {
  local cmd="$1"
  local sleep_per_char
  sleep_per_char=$(awk "BEGIN { printf \"%f\", 1/$BRUNCH_TYPE_CPS }")
  printf '\033[1;%sm$\033[0m ' "$BRUNCH_PROMPT_COLOR"
  local i ch
  for (( i=0; i<${#cmd}; i++ )); do
    ch="${cmd:$i:1}"
    printf '%s' "$ch"
    sleep "$sleep_per_char"
  done
  printf '\n'
  eval "$cmd"
  sleep "$BRUNCH_POST_LINE_PAUSE"
}

demo_say() {
  local text="$1"
  printf '\033[2;37m# '
  local i ch
  for (( i=0; i<${#text}; i++ )); do
    ch="${text:$i:1}"
    printf '%s' "$ch"
    sleep 0.025
  done
  printf '\033[0m\n'
  sleep 0.6
}

demo_pause() { sleep "${1:-1.5}"; }

clear
HELPERS

# ---------------------------------------------------------------------------
# Recording helpers.
# ---------------------------------------------------------------------------
mkdir -p "$CASTS_DIR"

# `record <name> <commands>` runs the given commands inside a fresh bash
# inside asciinema. Commands should normally be `type_cmd '<cmd>'` lines;
# anything else is fine but won't get the typewriter treatment.
record() {
  local name="$1"
  local commands="$2"
  local cast="$CASTS_DIR/$name.cast"
  echo "→ recording $name ..."
  rm -f "$cast"
  # Compose the session: source helpers, then run the step's commands.
  local session
  session="source $HELPERS_FILE
$commands
exit
"
  PS1='' \
    BRUNCH_TYPE_CPS="$TYPE_CPS" \
    BRUNCH_POST_LINE_PAUSE="$POST_LINE_PAUSE" \
    BRUNCH_CAST_COLS="$CAST_COLS" \
    BRUNCH_CAST_ROWS="$CAST_ROWS" \
    asciinema rec \
      --overwrite \
      --cols "$CAST_COLS" \
      --rows "$CAST_ROWS" \
      --idle-time-limit "$IDLE_TIME_LIMIT" \
      --title "brunch walkthrough — $name" \
      --command "bash --noprofile --norc -i" \
      "$cast" <<< "$session"
}

# ---------------------------------------------------------------------------
# Steps. Each one builds a small bash session that drives the demo.
# ---------------------------------------------------------------------------
TASKS_DIR="$HOME/repos/acme/tasks"
mkdir -p "$TASKS_DIR"

step_00_setup() {
  record 00-setup "$(cat <<EOF
demo_say 'brunch is installed; let us confirm the version and config.'
type_cmd 'brunch --version'
type_cmd 'cat \$XDG_CONFIG_HOME/brunch/config.toml'
demo_say 'and the canonical clones it expects to find:'
type_cmd 'ls \$HOME/repos/brunch/github.com/acme'
demo_say 'plus the template we will use:'
type_cmd 'cat \$XDG_CONFIG_HOME/brunch/templates/acme-fullstack.toml'
EOF
)"
}

step_01_create() {
  record 01-create "$(cat <<EOF
type_cmd 'cd $TASKS_DIR'
type_cmd 'brunch init $DEMO_TASK -t acme-fullstack'
demo_say 'the workspace dir + both worktrees materialised in one command.'
type_cmd 'ls $DEMO_TASK'
type_cmd 'cat $DEMO_TASK/brunch.toml'
EOF
)"
}

step_02_inspect() {
  record 02-inspect "$(cat <<EOF
type_cmd 'cd $TASKS_DIR/$DEMO_TASK'
type_cmd 'brunch status'
demo_say 'and a deeper health check:'
type_cmd 'brunch fsck'
EOF
)"
}

step_03_claude_code() {
  record 03-claude-code "$(cat <<EOF
type_cmd 'cd $TASKS_DIR/$DEMO_TASK'
demo_say 'starting Claude Code with the workspace as cwd:'
demo_say 'the agent sees both repos as direct siblings.'
type_cmd 'ls'
demo_say '(running \`claude\` here would open an interactive session;'
demo_say 'we mock that bit — see the page narrative for a sample diff.)'
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
type_cmd 'cd $TASKS_DIR/$DEMO_TASK'
type_cmd 'brunch foreach -- python -m pytest -q'
demo_say 'all green — let us confirm the workspace state too:'
type_cmd 'brunch status'
EOF
)"
}

step_05_commit() {
  record 05-commit "$(cat <<EOF
type_cmd 'cd $TASKS_DIR/$DEMO_TASK'
type_cmd 'brunch foreach -- git add -A'
type_cmd 'brunch foreach -- git status --short'
demo_say 'commit per repo, with a meaningful message each:'
type_cmd '( cd backend  && git commit -q -m "feat: add /api/v1/users/export CSV endpoint" )'
type_cmd '( cd frontend && git commit -q -m "feat(users): add Download CSV button" )'
demo_say 'and a quick log sanity check (GIT_PAGER=cat keeps less out of the way):'
type_cmd 'brunch foreach -- git log --oneline -2'
EOF
)"
}

step_06_push() {
  # Wire each worktree's origin to its bare remote so push actually works.
  for repo in backend frontend; do
    git -C "$TASKS_DIR/$DEMO_TASK/$repo" remote add origin "$REMOTES_DIR/$repo.git" 2>/dev/null || true
  done
  record 06-push "$(cat <<EOF
type_cmd 'cd $TASKS_DIR/$DEMO_TASK'
type_cmd 'brunch foreach -- git push -u origin HEAD'
demo_say 'both branches up; status reflects the push:'
type_cmd 'brunch status'
EOF
)"
}

step_07_pr() {
  record 07-pr "$(cat <<EOF
type_cmd 'cd $TASKS_DIR/$DEMO_TASK'
demo_say 'one PR per repo via gh, fanned out by brunch foreach:'
type_cmd 'brunch foreach -- gh pr create --fill --base main'
EOF
)"
}

step_08_teardown() {
  record 08-teardown "$(cat <<EOF
type_cmd 'cd $TASKS_DIR'
type_cmd 'brunch rm -w $DEMO_TASK'
demo_say 'worktrees gone, workspace dir gone, branches preserved in the canonicals.'
type_cmd 'ls $TASKS_DIR'
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
