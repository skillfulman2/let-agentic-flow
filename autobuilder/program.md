# autobuilder

This is an experiment to have the LLM build web apps autonomously.

## Setup

To set up a new experiment, work with the user to:

1. **Agree on a run tag**: propose a tag based on today's date (e.g. `mar13`). The branch `autobuilder/<tag>` must not already exist — this is a fresh run.
2. **Create the branch**: `git checkout -b autobuilder/<tag>` from current master.
3. **Read the in-scope files**: Read these files for full context:
   - `autobuilder/program.md` — this file, your instructions.
   - `autobuilder/evaluate.py` — fixed evaluation harness. Do not modify.
   - `autobuilder/tests/` — fixed Playwright tests. Do not modify.
   - `autobuilder/app/src/` — the SvelteKit source you will modify.
   - `autobuilder/feedback/` — user feedback transcripts, if any.
4. **Verify app builds**: Run `cd autobuilder/app && npm run build` to confirm the app compiles.
5. **Initialize results.tsv**: Create `autobuilder/results.tsv` with just the header row.
6. **Confirm and go**: Confirm setup looks good.

Once you get confirmation, kick off the experimentation.

## Experimentation

Each experiment is evaluated by running: `python autobuilder/evaluate.py`

This builds the SvelteKit app, starts a preview server, runs Playwright tests, and produces a composite score (0-100).

**What you CAN do:**
- Modify anything in `autobuilder/app/src/` — routes, components, layouts, styles, lib code.
- Modify anything in `autobuilder/app/static/` — manifest, icons, static assets.

**What you CANNOT do:**
- Modify `autobuilder/tests/` — these are the fixed evaluation tests.
- Modify `autobuilder/evaluate.py` — this is the fixed harness.
- Modify `autobuilder/app/package.json` — dependencies are fixed.
- Modify `autobuilder/playwright.config.ts` — test config is fixed.
- Modify `autobuilder/app/svelte.config.js` or `autobuilder/app/vite.config.ts`.

**The goal is simple: get the highest score (0-100).** The score is a composite of Playwright test pass rate and Lighthouse audit scores (performance, accessibility, best practices, SEO — equally weighted at 25% each). All Playwright tests must pass for the full Lighthouse score to count; any failure caps the score at 50.

**Feedback**: Before each iteration, check `autobuilder/feedback/` for user feedback transcripts. Prioritize recent entries. The user may record voice notes describing what they want changed — treat these as high-priority directives.

**Simplicity criterion**: All else being equal, simpler is better. A small improvement that adds ugly complexity is not worth it. Conversely, removing something and getting equal or better results is a great outcome. When evaluating whether to keep a change, weigh the complexity cost against the improvement magnitude.

**The first run**: Your very first run should always be to establish the baseline, so you will run the evaluation as-is.

## Output format

The evaluation script prints a summary like this:

```
---
score:            97.5
build_time_ms:    1162
total_seconds:    16.0
tests_passed:     12
tests_failed:     0
tests_total:      12
lh_performance:   100
lh_accessibility: 100
lh_best_practices: 100
lh_seo:           90.0
```

You can extract key metrics from the log file:

```
grep "^score:\|^lh_" run.log
```

## Logging results

When an experiment is done, log it to `autobuilder/results.tsv` (tab-separated, NOT comma-separated — commas break in descriptions).

The TSV has a header row and 5 columns:

```
commit	score	build_ms	status	description
```

1. git commit hash (short, 7 chars)
2. score achieved (e.g. 85.7) — use 0.0 for crashes
3. build time in ms (e.g. 2340) — use 0 for crashes
4. status: `keep`, `discard`, or `crash`
5. short text description of what this experiment tried

Example:

```
commit	score	build_ms	status	description
a1b2c3d	71.4	2340	keep	baseline
b2c3d4e	85.7	2100	keep	add page title and meta tags
c3d4e5f	64.3	2500	discard	refactored routing (broke links)
d4e5f6g	0.0	0	crash	invalid svelte syntax
```

## The experiment loop

The experiment runs on a dedicated branch (e.g. `autobuilder/mar13`).

LOOP FOREVER:

1. Look at the git state: the current branch/commit we're on
2. Read any new feedback in `autobuilder/feedback/`
3. Modify files in `autobuilder/app/src/` or `autobuilder/app/static/` with an improvement idea
4. git commit
5. Run evaluation: `python autobuilder/evaluate.py > run.log 2>&1` (redirect everything — do NOT use tee or let output flood your context)
6. Read out the results: `grep "^score:\|^tests_\|^lh_" run.log`
7. If the grep output is empty, the run crashed. Run `tail -n 50 run.log` to read the error and attempt a fix. If you can't get things to work after more than a few attempts, give up.
8. Record the results in the TSV (NOTE: do not commit the results.tsv file, leave it untracked by git)
9. If score improved (higher), you "advance" the branch, keeping the git commit
10. If score is equal or worse, you git reset back to where you started

The idea is that you are a completely autonomous developer trying things out. If they work, keep. If they don't, discard. And you're advancing the branch so that you can iterate.

**Timeout**: Each evaluation should take ~30-60 seconds total. If a run exceeds 5 minutes, kill it and treat it as a failure (discard and revert).

**Crashes**: If a run crashes (build failure, broken syntax, etc.), use your judgment: If it's something dumb and easy to fix (e.g. a typo, a missing import), fix it and re-run. If the idea itself is fundamentally broken, just skip it, log "crash" as the status in the TSV, and move on.

**NEVER STOP**: Once the experiment loop has begun (after the initial setup), do NOT pause to ask the human if you should continue. Do NOT ask "should I keep going?" or "is this a good stopping point?". The human might be asleep, or gone from a computer and expects you to continue working *indefinitely* until you are manually stopped. You are autonomous. If you run out of ideas, think harder — re-read the test files to understand what's being evaluated, try different approaches, address any feedback. The loop runs until the human interrupts you, period.
