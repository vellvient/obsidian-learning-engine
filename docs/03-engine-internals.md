# 03 — Engine Internals (FSRS v6 + chain-weighted FIRe)

Everything in `srs_fsrs.py` — a zero-dependency, standard-library implementation.

## The card model

Review cards live in `.obsidian/srs_state.json` under `reviews`, keyed by
`"{file}.md:{subskill id}: {subskill name}"`. Each card carries **two** scheduling
systems side by side:

```json
{
  "file": "7 - solving-two-step-equations.md",
  "skill": "7a: Solve ax + b = c.",
  "ticked_at": "2026-07-01T09:00:00",
  "review_stages": [ {"due": "...", "stage": 1}, ... ],   // legacy fixed ladder
  "fsrs": {
    "state": 2, "stability": 3.0, "difficulty": 4.5,
    "due": "...", "last_review": "...",
    "history": [{"rating": 3, "at": "...", "iv": 3}]
  }
}
```

- **Legacy ladder**: fixed intervals of **1 / 3 / 7 / 14 / 30 days** from the tick
  date (5 stages, then retired). Kept for transparency and as the seed source.
- **FSRS v6**: the modern scheduler — per-card `stability` (how long memory lasts)
  and `difficulty`, updated by grading `Again / Hard / Good / Easy`. FSRS `due`
  supersedes the ladder once a card is seeded.

## CLI surface

```bash
python srs_fsrs.py --stats          # dual counts: FSRS due + legacy overdue
python srs_fsrs.py --due            # due list after compression + relearning-lock
python srs_fsrs.py --grade "<file>.md:<skill>" <Again|Hard|Good|Easy>
python srs_fsrs.py --grader-note    # regenerate 00 - Review Grader.md (oldest first, cap 40)
python srs_fsrs.py --tracker        # regenerate 00 - SRS Review Tracker.md
python srs_fsrs.py --migrate [--dry]  # seed fsrs for cards missing it (idempotent)
python srs_fsrs.py --reseed  [--dry]  # OVERWRITE all fsrs S/due from earliest overdue stage
```

## Scheduler rules beyond vanilla FSRS

1. **Compression** — the due list groups sub-skills by note so one sitting reviews a
   coherent unit instead of scattered atoms.
2. **Relearning-lock** — a lapse (`Again`) puts the card in Relearning state, and its
   *dependents* are hidden from the due list until the prerequisite recovers. You
   never get quizzed on quadratics while linear equations are relearning.
3. **Retrieval-proof mastery gate** — 100% checkboxes alone caps a note at
   `proficient`; promotion to `mastered` requires Good/Easy grades in FSRS history.

## Chain-weighted FIRe (Fractional Implicit Repetition)

The idea (from Math Academy): **practicing a skill implicitly reviews its
prerequisites** — so give the ancestors fractional review credit instead of asking
for redundant explicit reviews.

Implementation in `VaultFSRS`:

- `ancestors_with_weights(child)` walks ALL ancestors via BFS. Chain weight =
  **product of edge weights along the path × decay^distance** (default edge weight
  0.3, default decay 0.5).
- `apply_fire_chain(child)` multiplies each ancestor's FSRS **stability** by
  `(1 + chain_weight)` and extends its `due` proportionally.
- Effect: a direct parent gets a meaningful boost (w=0.30 at distance 1); a
  grandparent gets a small one (0.3 × 0.3 × 0.5 = 0.045 at distance 2). Credit
  fades naturally with distance — no cliff, no double-counting.

Custom per-edge weights go in note frontmatter:

```yaml
implicit_review:
  - [4, 0.5]    # expanding brackets gets 50% credit when this skill is practiced
  - [7, 0.25]
```

If `implicit_review` is absent it defaults to `prerequisites` (weight 0.3 each).
Keep the two fields in sync — `fire_populate.py` mirrors prerequisites into
`implicit_review` for notes missing it.

When does FIRe fire? On every tick the (optional) watcher grades the sub-skill
`Good` and runs the chain boost; manually, `flow_diagnostic.py --apply-fire`
re-applies it for reviews ticked in the last 24h (also part of `evening.py`).

## The catch-up strategy (when you fall behind)

Default to **learn-new-first, ranked by unlock value and decayed-material reuse** —
not a raw SRS grind. Rationale and limits, measured on the reference vault:

- Learning a new skill FIRe-reviews its decayed prerequisites *for free* — but only
  prerequisites of something unfinished can be absorbed this way. Empirically only
  ~24 of ~189 decayed skills sat under unfinished dependents; the rest are **leaves
  that need direct review**. So: learn-new first, then a short direct-review tail.
- Keep a **minimum review floor** (10–15 cards/day) even in maximum-learn-new mode,
  so FSRS stays honest and relearning-lock can fire.
- Rank what to learn with `scripts/unlock_priority.py`. Trust order:
  `FULLY_UNBLOCKS` (sole remaining gate) > `IN_DEGREE` (hub) > `DOWNSTREAM`
  (misleading — collapses onto graph roots). Mastered hubs are flagged: their value
  is already realized, don't re-prioritize them.
- Measure the real backlog with `scripts/srs-backlog.py` — dashboards truncate their
  due tables; the backlog script counts everything, grouped by due date, oldest first.

## The reseed lesson (trust but verify your scheduler)

The reference build shipped a seeding bug: migration seeded every card from
`max(stage)` (always 5) → uniform S=30, everything due in ~30 days → the dashboard
said **"0 due"** while 300+ legacy stages were overdue. The fix (`--reseed`) seeds
from the **earliest overdue stage** and sets `due=now` for overdue cards.

Takeaway that generalizes: **never trust "0 due" alone.** Cross-check
`--stats` against `scripts/srs-backlog.py`; if all dues sit ~30d out with identical
stability, reseed.

## Daily wrappers

- `morning.py` — study_today + dual SRS stats + regenerate grader + tracker + micro-drill bridge.
- `evening.py` — mastery sync + diagnostic regeneration + FIRe re-apply + tracker + sprint status.

Both are thin `subprocess` chains over the atomic tools — read them to see the exact order.
