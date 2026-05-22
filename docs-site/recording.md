# Recording the casts

Every page in the [walkthrough](walkthrough/index.md) embeds a short
asciinema cast at `docs-site/assets/casts/<step>.cast`. The casts are
committed alongside the markdown — but they're easy to regenerate.

## One-shot rebuild

```bash
./scripts/record-walkthrough.sh
```

That's it. The script:

1. **Spins up an isolated demo environment** under `/tmp/brunch-walkthrough/` —
   fake `$HOME`, fake canonical clones for `acme/backend` and `acme/frontend`,
   the `acme-fullstack` template installed.
2. **Stubs out anything network-dependent**: `gh pr create` is shimmed to
   print a plausible PR URL; `git push` targets bare repos on disk that
   pretend to be `origin`. Nothing leaves your machine.
3. **Forces a known terminal size and pacing** so the casts are legible
   regardless of where you run the script (see [Pacing and sizing](#pacing-and-sizing)
   below).
4. For each tutorial step, runs `asciinema rec --cols 80 --rows 40 …`
   with a typewriter-driven session.

Re-running overwrites the cast files in place; the markdown doesn't
change.

## Prerequisites

- **`asciinema` 3.0+** — strictly required for `--window-size`. The
  catch: asciinema 3.x is a Rust rewrite and **isn't on PyPI** (the
  series got abandoned at 2.4.0 in Aug 2023). `uv tool install
  asciinema` / `pipx install asciinema` / `pip install asciinema` all
  pull the old version. Debian and Ubuntu repos are similarly stuck.

    Use the bundled installer to drop the upstream binary under
    `tools/asciinema` (gitignored, project-local, no sudo, no PATH
    juggling against the OS-installed 2.x):

    ```bash
    ./scripts/install-asciinema.sh
    ```

    Bumps to a newer pinned version:

    ```bash
    ASCIINEMA_VERSION=3.3.0 ./scripts/install-asciinema.sh
    ```

    The recording script automatically prepends `tools/` to `$PATH`
    when this binary exists, so `./scripts/record-walkthrough.sh` Just
    Works after a successful install. It also checks the version at
    startup and bails with the install hint above if something is too
    old.

- `git`, `awk`, `python`, and `uv` — `git` for the demo repos, `awk` for
  the typewriter's per-char delay computation, `python` for the demo
  test suite, `uv` for installing brunch into the isolated env.

## Pacing and sizing

The script gets three things right that a naive `asciinema rec -c "…"`
doesn't:

### 1. Typewriter pacing

Commands appear character-by-character at human typing speed. Without
this, the heredoc-fed input lands instantly through the pty and the
viewer can't read a thing.

This is done by a `type_cmd` bash function sourced into every recorded
session (the helper file lives at
`$DEMO_ROOT/demo-helpers.sh` while recording). Each step's session
looks like:

```bash
source $DEMO_ROOT/demo-helpers.sh
type_cmd 'brunch status'
demo_say 'and a deeper health check:'
type_cmd 'brunch fsck'
exit
```

`type_cmd` prints the command to stdout char-by-char with a sleep
between each, then `eval`s it. `demo_say` does the same for narrative
comments (rendered as `# dim grey text`). `demo_pause [seconds]` adds
an explicit beat.

### 2. Fixed terminal size

`asciinema rec --window-size 80x40` ignores the host terminal's actual
size and records a fixed 80×40 canvas. The asciinema-player on the
docs site scales that to the page width, which looks good across
viewports.

**You don't need to resize your terminal panel** — Zed's panel can be
any size, the cast will still be 80×40.

### 3. No pagers

`git log` defaults to invoking `less`, which would flash up a pager UI
inside the cast and steal the keyboard. The helper file exports
`GIT_PAGER=cat` and `PAGER=cat` so every paging tool in the recorded
session writes to stdout directly.

## Tuning the pacing

The four pacing knobs are env vars; the defaults are tuned for
walkthrough-style demos:

| Variable | Default | What it does |
|---|---|---|
| `BRUNCH_TYPE_CPS` | `22` | Typewriter speed in characters per second (`22` ≈ 45 ms/char, deliberate but not painful). |
| `BRUNCH_POST_LINE_PAUSE` | `0.8` | Seconds to wait after a command's output before the next prompt. |
| `BRUNCH_IDLE_TIME_LIMIT` | `3` | `--idle-time-limit` passed to `asciinema rec`; idle gaps longer than this are collapsed during playback. |
| `BRUNCH_CAST_COLS` / `BRUNCH_CAST_ROWS` | `80` / `40` | Recording canvas dimensions. |

To slow everything down for a particularly fiddly step:

```bash
BRUNCH_TYPE_CPS=14 BRUNCH_POST_LINE_PAUSE=1.5 ./scripts/record-walkthrough.sh
```

To speed it up if it feels turgid:

```bash
BRUNCH_TYPE_CPS=35 BRUNCH_POST_LINE_PAUSE=0.4 ./scripts/record-walkthrough.sh
```

## Customising individual steps

Each step is a small bash function (`step_00_setup`, `step_01_create`,
…). To tweak one:

- Add or remove `type_cmd '<cmd>'` lines.
- Insert `demo_say '<note>'` for a slow narrative comment between
  commands.
- Drop in a `demo_pause 2` to hold on a particularly information-dense
  bit of output.
- Override per-step env vars by prefixing the `record` call —
  e.g., to type the `init` step extra-slowly, change `step_01_create` to
  prefix `BRUNCH_TYPE_CPS=14` before calling `record`.

## Embedding the resulting casts elsewhere

The casts are plain JSON-line files following the [asciicast
format](https://docs.asciinema.org/manual/asciicast/v2/). You can:

- Embed them in any site that loads `asciinema-player`.
- Link directly to them from a README via `[![asciicast](https://asciinema.org/a/<id>.svg)](…)`
  once uploaded.
- Convert to GIF with [`agg`](https://github.com/asciinema/agg):
  `agg --cols 80 --rows 40 <step>.cast <step>.gif`.
