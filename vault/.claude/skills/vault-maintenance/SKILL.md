---
name: vault-maintenance
description: Day-to-day operation of a learning-engine vault — mastery-tag sync (all 4 places), FSRS/FIRe upkeep, catch-up planning when behind schedule, index maintenance, and the known failure modes. Use when ticking sessions need processing, mastery tags look wrong, the SRS seems off, or the user asks "what should I study to catch up".
version: 1.0.0
license: MIT
platforms: [windows, macos, linux]
---

# Vault Maintenance — operating the learning engine

The construction methodology lives in the sibling `knowledge-graph` skill; this
skill is for the *running* vault. Commands are run from the vault root.

## The 4-place mastery sync (most common repair)

A note's mastery is stored in FOUR places with different consumers; they drift when
anything is patched by hand:

| Place | Consumer |
|---|---|
| `mastery:` frontmatter | engine scripts |
| `tags:` frontmatter (inline `[x, y]` OR multi-line list — handle both) | Obsidian tag pane |
| Body `#tag` line | Obsidian **graph coloring** |
| `Mastery: **X**` display line (+ `(n/m)` counter) | the human |

Fix everything at once: `python flow_diagnostic.py --sync-mastery` (also inside
`evening.py`). Rules it enforces:
- Mastery is computed from checkbox truth — recount `- [x]` lines, never trust labels.
- 100% checkboxes alone caps at `proficient`; `mastered` requires Good/Easy FSRS history.
- When patching manually anyway, use disambiguating context (`"tags: [familiar, "`,
  `"\n#familiar\n"`, `"**Familiar** ("`) — fuzzy matching on the bare word
  cross-matches the wrong copy.

## Processing a study session (when ticks arrived without the watcher)

1. Identify ticked subskills (`git diff HEAD~1 HEAD -- <files>` shows `[ ]`→`[x]`;
   distinguish first-time ticks from review re-ticks — re-ticks change no checkboxes,
   only FSRS metadata).
2. Grade honest difficulty for anything shaky:
   `python srs_fsrs.py --grade "<file>.md:<skill>" Again|Hard|Good|Easy`
   (`Again` → relearning state → dependents hidden until recovery).
3. `python evening.py` — sync + diagnostic + FIRe + tracker.
4. Commit note files only — **never `git add` `.obsidian/srs_state.json`**.

## SRS health

- Real backlog: `python scripts/srs-backlog.py` (dashboards truncate their tables).
- **Never trust "0 due" alone.** If `--stats` shows every card at identical stability
  with dues clustered ~30d out, the seeding is broken: `python srs_fsrs.py --reseed`
  (re-derives S/due from the earliest overdue legacy stage). `--migrate` only fills
  *missing* fsrs objects; it cannot repair bad ones.
- Correct legacy ladder: **1/3/7/14/30 days**.
- `implicit_review:` should mirror `prerequisites:` (custom weights excepted) —
  `python fire_populate.py` fills gaps.

## Catch-up planning (user is behind)

Default to **learn-new-first ranked by unlock value**, not an SRS grind:

1. Measure the backlog (`scripts/srs-backlog.py`), oldest cohort first.
2. Check the absorption ceiling: only decayed skills that are prerequisites of
   *unfinished* topics get free FIRe review from new learning (reference build:
   ~24 of 189). The rest are leaves → schedule a short direct-review tail.
3. Rank new topics: `python scripts/unlock_priority.py --frontier --top 20`.
   Trust `FULLY_UNBLOCKS` > `IN_DEGREE` > `DOWNSTREAM` (downstream collapses onto
   roots). Ignore `[mastered]`-flagged hubs — value already realized.
4. Keep a 10–15 card/day review floor so FSRS stays honest and relearning-lock works.
5. Sprints are menus, not calendars — retention beats coverage when behind.

## Index & dashboard upkeep

- AUTO notes (`Flow Zone Diagnostic`, `Review Grader`, `SRS Review Tracker`,
  `practice/*`) — regenerate, never hand-edit.
- `00 - Master Index.md` is manual: update topic mastery levels after sessions;
  correct subskill totals from `flow_diagnostic.py --json` (labels drift).
- Sprint plan status columns are manual; `python scripts/sprint_status.py` reports
  checkbox truth to update them from. Match existing table formatting exactly —
  stray `|` breaks tables.

## Known failure modes (fast diagnosis)

| Symptom | Cause → fix |
|---|---|
| Graph colors wrong for one note | Body `#tag` out of sync → `--sync-mastery` |
| Graph colors ALL gray | `#not-started` group ordered before mastery groups in graph.json |
| graph.json keeps reverting | Obsidian is open — close it, write, reopen |
| "0 due" but you feel rusty | Seeding bug → `--stats` + `srs-backlog.py`, then `--reseed` |
| UnicodeEncodeError on script run | Non-UTF8 console; scripts are guarded — a new unguarded script needs `sys.stdout.reconfigure(errors="replace")` |
| Grade command "not found" key | Key is exact `"{file}.md:{skill line}"` incl. trailing period — copy from `00 - Review Grader.md` |
| Duplicate note files, same id | Slugify drift during bulk generation → keep the linked one, delete the orphan, re-run verify_engine |
| Broken (greyed) wikilinks in indexes | Links built from re-derived names → rebuild from actual file stems via glob |

## Verification after any bulk change

```bash
python scripts/verify_engine.py    # full engine self-test (must pass)
python srs_fsrs.py --stats         # sane dual counts
python study_today.py              # sane ranking
```

Keep docs in sync: any new CLI flag or behavior change also updates `AGENTS.md`
in the same change — a stale operator doc makes the next agent rebuild instead of extend.
