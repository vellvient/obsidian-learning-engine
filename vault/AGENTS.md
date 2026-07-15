# Learning Vault — Agent Context

> Purpose: prerequisite knowledge graph + FSRS + FIRe + micro-drills for mastery
> learning (a self-hosted Math Academy-style loop).
> If you are an AI agent working in this vault: read this file fully before changing
> SRS, diagnostic, or study-workflow behavior. The full handbook is in `../docs/`.

## What this vault is

One note per skill (`{num} - {slug}.md`, flat at root), lettered sub-skill
checkboxes as the unit of mastery/SRS, typed prerequisite edges in
`.engine/prerequisite_edges.json` + note frontmatter. The vault currently contains
the **Algebra Basics demo** (notes 1–15) — replace it with a real subject via the
build phases below.

Learning stack:

1. **Knowledge graph** — `prerequisites` / `leads-to` frontmatter, checkbox subskills
2. **Flow-zone diagnostic** — `flow_diagnostic.py`
3. **FSRS v6 + chain FIRe** — `srs_fsrs.py` (+ optional `../automation/srs_watcher.py`)
4. **CCT micro-schemas** — `micro_trainer/`
5. **Daily wrappers** — `morning.py` / `evening.py`

## Daily commands (source of truth)

```bash
python morning.py                      # study plan + grader + tracker + micro bridge
python evening.py                      # sync mastery, diagnostic, FIRe, tracker, sprints
python study_today.py --top 12 --frontier
python srs_fsrs.py --stats | --due | --reseed | --grader-note | --tracker | --grade "key" Good
python flow_diagnostic.py --markdown | --sync-mastery | --apply-fire
python log_error.py <num> "what went wrong" [--shot] [--again] [--sev X]
python micro_bridge.py
python scripts/sprint_status.py | scripts/srs-backlog.py
python scripts/unlock_priority.py --frontier --top 20
python scripts/verify_engine.py        # full engine self-test
python micro_trainer/train.py --list
python cockpit_app.py                   # localhost GUI over the same engine/state
```

| Note | Role |
|------|------|
| `00 - Flow Zone Diagnostic.md` | Daily plan (AUTO — never hand-edit) |
| `00 - Review Grader.md` | Due cards with copy-paste grade commands (AUTO) |
| `00 - SRS Review Tracker.md` | Schedule view (AUTO) |
| `00 - Error Log.md` | Error capture target + `/error-triage` queue |
| `00 - Weak Spots Priority.md` | Updated by `/error-triage` |
| `00 - Master Index.md` | Manual topic overview |

## Building a new subject (agent-executable)

Follow `../docs/02-build-pipeline.md`; the mining methodology is in
`.claude/skills/knowledge-graph/`. Phase summary + manual fallbacks:

1. **Extract** the curriculum to `{num, name, topic, domain, subskills[]}` JSON.
   *Manual fallback:* type the skill list from a syllabus by hand — 60–120 rows is an
   afternoon and worth it.
2. **Generate** one note per skill matching the demo notes' exact shape (frontmatter
   fields, body `#tag`, checkbox format). *Freeze one slugify function first.*
3. **Mine edges**: `scripts/graph_pipeline/prereq_batch_processor.py --generate`,
   process batches with an LLM, **validate** (cycles/dangling/transitive-reduction),
   then `--merge` and `--apply`. *Manual fallback:* hand-fill `prerequisites:` in
   frontmatter and run `--apply` to mirror them to bodies/edges.
4. **Aggregate**: `scripts/graph_pipeline/aggregate_topics.py`.
5. **Color**: edit `.obsidian/graph.json` — ONLY with Obsidian closed.
6. **Verify**: `python scripts/verify_engine.py` must pass; then `python morning.py`.

Then delete the demo notes (1–15, Expressions.md, Equations.md), reset
`srs_state.json` `reviews` to `{}`, and reset `.engine/prerequisite_edges.json`.

## Mastery rules

- Checkboxes drive progress; sync updates **4 places** (`mastery:`, `tags:`,
  body `#tag`, display text) — use `--sync-mastery`, never patch one place.
- 100% boxes alone → `proficient` max; `mastered` needs retrieval proof (Good/Easy
  FSRS history).
- Ladder: `not-started → attempted → familiar → proficient → mastered`.

## Hard constraints

- **Never** hand-edit or hand-commit `.obsidian/srs_state.json` (engine-owned).
- **Never** regenerate `graph.json` while Obsidian is open.
- AUTO-marked notes are regenerated — never hand-edit them; change the generator.
- Idempotent inserts into hand-written notes use `<!-- auto:... -->` marker blocks —
  replace only within markers.
- All scripts print console-safely (`sys.stdout.reconfigure(errors="replace")`);
  keep new scripts ASCII-safe in `print()`.
- Review-vs-new policy: prefer new flow-zone topics that FIRe-review decayed
  prerequisites, keep a 10–15 card/day direct-review floor, and finish with a short
  direct-review tail for decayed leaves (they have no dependents to absorb them).

## Optional: past-paper practice (Phase 7)

With your own PDFs: see `../docs/05-paper-pipeline.md`. Pipeline order: `extract.py
--src ... --years ...` → `extract.py --batches` → `process_batches.py` →
`merge_bank.py` → `render_questions.py` (question PNGs **and** per-question
mark-scheme crops) → optional `latexify_answers.py` (LaTeX finals) →
`gen_practice.py`. Per node it generates `practice/{num} - Practice.md` (LaTeX
final line + MS crop image in a folded callout) + `papers/booklets/{num} -
Booklet.pdf` (each question followed by its MS crop, same page when it fits) + a
marker block in the note; `study_today.py` marks such picks with `p`. Serve
interactively with `python quiz.py` (flow-zone/due selection, self-grades wired to
FSRS, misses to the error log). Bank/renders/booklets are gitignored (copyrighted
source material stays local).

## Local Learning Cockpit

`cockpit_app.py` and `cockpit_engine.py` provide a dependency-free localhost UI.
Course targets drive coverage; HARD/SOFT ancestors remain eligible as support
skills. `config/causal_bridges.json` can add reviewable diagnostic relationships
without changing the canonical gating DAG. Personal GUI state lives in
`papers/cockpit_state.json` and must remain gitignored. See
`LEARNING_COCKPIT_WALKTHROUGH.md`.

## Skills available to agents

- `.claude/skills/knowledge-graph/` — full graph-building methodology + validation gate
- `.claude/skills/error-triage/` — batch error analysis (`/error-triage`)
- `.claude/skills/vault-maintenance/` — day-to-day ops: mastery sync details,
  catch-up strategy, index upkeep, known failure modes
