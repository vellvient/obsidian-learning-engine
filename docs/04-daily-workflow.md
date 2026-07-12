# 04 — Daily Workflow

The loop the whole system exists to serve. Total overhead: ~2 minutes of terminal
time per day; everything else is studying.

## Morning

```bash
cd vault
python morning.py
```

Prints, in order: FSRS due counts, the **Review Grader** pointer, the ranked
`study_today` table (flow zone × unlock leverage, `*` = in-progress closest wins,
`!` = weak-spot boost, `p` = has practice material), and micro-drill commands
matched to today's picks.

**Session order** (the empirically good default):

1. **Review Grader first** — open `00 - Review Grader.md`, grade 20–30 oldest cards
   (`Again` if shaky — honesty here is what makes everything else work).
2. **Finish in-progress** (`*` rows) — closest wins, don't let them go cold.
3. **Top 2 flow-zone rows** — work through all sub-skills, ticking checkboxes in
   Obsidian as you verify each one.
4. **5–10 min micro-drills** — the suggested `micro_trainer/train.py` commands.

## During study — capture errors in 5 seconds

The moment you get something wrong, log it and move on. **No analysis mid-session** —
that's batch work for later.

```bash
python log_error.py 7 "subtracted before dividing - inverse op order"
python log_error.py 7 "sign slip on both-sides subtraction" --shot --again
```

- `--shot` attaches your latest screenshot (drop it in the vault's `attachments/errors/`).
- `--again` immediately FSRS-grades the sub-skill `Again` (triggers relearning-lock).
- Entries land in `00 - Error Log.md` tagged `#unanalyzed`.

## Grading reviews

Grading is a terminal command (protocol-link buttons inside Obsidian notes don't
work — see pitfalls):

```bash
python srs_fsrs.py --grade "7 - solving-two-step-equations.md:7a: Solve ax + b = c." Good
```

The grader note gives you copy-paste blocks for everything due. Grade meaning:
`Again` = failed (relearning + lock dependents), `Hard` = barely, `Good` = normal
recall, `Easy` = instant.

## Evening

```bash
python evening.py
```

Syncs mastery tags from checkbox truth (all 4 places), regenerates the flow-zone
diagnostic + tracker, re-applies FIRe for today's ticks, and prints sprint status.

## End of session (or week) — error triage

With an AI agent, run the shipped skill:

```
/error-triage
```

It reads every `#unanalyzed` entry (including screenshots), classifies each error
into one of six types — Slip / Procedural bug / Concept gap / Prerequisite gap /
Strategy blank / Misread — root-causes prerequisite gaps via the graph, prescribes a
rehearsable rule per error, updates `00 - Weak Spots Priority.md`, offers
`--grade ... Again` commands, and names the single highest-leverage fix.

Weak-spot notes then get a ranking boost in `study_today.py` (`!` marker), closing
the loop: mistakes → analysis → prioritized re-study.

## Weekly-ish upkeep

- `python scripts/srs-backlog.py` — true backlog check (dashboards truncate).
- `python scripts/unlock_priority.py --frontier --top 20` — re-rank what unlocks most.
- `python scripts/verify_engine.py` — full engine self-test after any bulk edit.
- Sprint plans (if you use them) are **menus, not calendars** — when behind, run
  catch-up order (see `03-engine-internals.md`), don't grind the calendar.

## Optional: full automation

`automation/srs_watcher.py` (hourly, via cron or Task Scheduler) git-detects checkbox
ticks, grades them `Good`, and runs the FIRe chain boost — so ticking a box in
Obsidian is all you have to do. Setup: `automation/README.md`. Manual grading remains
the honest path for anything you struggled with (the watcher only sees successful ticks).
