# Recording the casts

Every page in the [walkthrough](walkthrough/index.md) embeds a short asciinema
cast at `docs-site/assets/casts/<step>.cast`. The casts are committed
alongside the markdown — but they're easy to regenerate if you ever
want a fresh recording (e.g. after a UI change in brunch's renderer).

## One-shot rebuild

```bash
./scripts/record-walkthrough.sh
```

That's it. The script:

1. Spins up an isolated environment under `/tmp/brunch-walkthrough/` —
   fake `$HOME`, fake canonical clones for `acme/backend` and
   `acme/frontend`, the `acme-fullstack` template installed.
2. Stubs out network-dependent commands: `gh pr create` becomes a
   pretend wrapper that prints a fake PR URL, `git push` targets a
   bare repo on disk. Nothing leaves your machine.
3. For each tutorial step, runs `asciinema rec --idle-time-limit 1 -c
   "<command>" docs-site/assets/casts/<step>.cast`.
4. Cleans up the temp environment afterwards.

Re-running the script overwrites the cast files in place; the markdown
doesn't change.

## Prerequisites for recording

- [`asciinema`](https://docs.asciinema.org/) (any 2.x or 3.x will do).
- `git`, `python` (for the fake test suites), and `uv` (the script
  builds an editable install of brunch into the demo env).
- A 80–120-column terminal — wider records also work, the embed
  resizes to fit.

## Customising

The script's structure is `step_NN_<name> {  …  }` shell functions, one
per page. To tweak a step:

- Change the `--idle-time-limit` (default 1s) to slow individual steps
  down for emphasis.
- Insert `sleep`/`echo` lines between commands to add narrative beats.
- Re-export `BRUNCH_DEMO_TASK=...` near the top to change the demo task
  name (everything downstream picks it up automatically).

## Embedding casts elsewhere

The casts are plain JSON-line files following the [asciicast
format](https://docs.asciinema.org/manual/asciicast/v2/). You can
embed them in any site that loads `asciinema-player`, link directly
to them from a README, or convert to GIF with
[`agg`](https://github.com/asciinema/agg) (`agg --idle-time-limit 1
<step>.cast <step>.gif`).
