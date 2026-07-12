# 06 — Automation (optional layer)

Everything works with just `morning.py` / `evening.py` run by hand. This layer makes
the SRS fully hands-off: **tick a checkbox in Obsidian, and the engine handles the rest.**

## The SRS watcher

`automation/srs_watcher.py`, run hourly:

1. Git-commits any vault changes (the vault should be its own git repo).
2. Diffs against the last-seen commit to find checkboxes that flipped `[ ]` → `[x]`.
3. For each newly ticked sub-skill: creates/advances its review card, FSRS-grades it
   **Good**, and runs the chain-weighted FIRe boost on its prerequisite ancestors.
4. Writes everything to `.obsidian/srs_state.json` (this is why that file is
   never hand-edited).

Invocation (vault path via argument or env var):

```bash
python automation/srs_watcher.py "C:\path\to\your\vault"
# or
LEARNING_VAULT=/path/to/vault python automation/srs_watcher.py
```

The watcher only sees *successful* ticks, so it can only grade `Good`. Anything you
struggled with should be graded manually (`Again`/`Hard`) — that's what keeps FSRS
honest and triggers relearning-lock.

## Scheduling it

**Linux/macOS (cron):**

```cron
0 * * * *  cd /path/to/vault && python /path/to/repo/automation/srs_watcher.py "$PWD"
0 7 * * *  cd /path/to/vault && python flow_diagnostic.py --markdown   # morning report
```

**Windows (Task Scheduler):**

```powershell
schtasks /Create /TN "SRS Watcher" /SC HOURLY ^
  /TR "python C:\path\to\repo\automation\srs_watcher.py C:\path\to\vault"
schtasks /Create /TN "Morning Diagnostic" /SC DAILY /ST 07:00 ^
  /TR "cmd /c cd /d C:\path\to\vault && python flow_diagnostic.py --markdown"
```

**Agent platforms:** if you run an agent framework with cron support (Claude Code
scheduled tasks, Hermes cron, etc.), schedule the same two commands there. The
reference setup ran the watcher every 60 minutes with silent/local delivery and the
diagnostic daily at 07:00.

## What NOT to automate

- **Grading difficulty** — only you know whether recall was shaky.
- **Mastery promotion to `mastered`** — requires retrieval proof; the sync logic
  handles it, but review its decisions rather than assuming.
- **graph.json regeneration** — must happen with Obsidian closed; keep it manual.

## Health checks

- The watcher commits with recognizable messages — `git log --oneline | head` shows
  whether it's alive.
- If a scheduled job silently stops (machine asleep, provider config drift), the
  symptom is a stale `00 - SRS Review Tracker.md` date. `scripts/srs-backlog.py`
  always tells the truth regardless of automation state.
- After any long outage, run `python srs_fsrs.py --stats` and compare FSRS-due with
  legacy-overdue; if they diverge wildly, see the reseed procedure in
  `03-engine-internals.md`.
