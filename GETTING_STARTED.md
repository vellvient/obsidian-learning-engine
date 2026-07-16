# Getting Started

Two tracks: **(A)** try the demo in 5 minutes, **(B)** build a vault for your own subject.

---

## Track A — Try the demo (5 minutes)

Requirements: Python 3.10+, Obsidian (free), git.

```bash
git clone https://github.com/vellvient/obsidian-learning-engine
cd obsidian-learning-engine/vault
python morning.py
```

You'll see a ranked study plan built from the demo "Algebra Basics" vault:
FSRS-due reviews, flow-zone picks ranked by unlock leverage, and micro-drill
suggestions. Then:

1. Open Obsidian → *Open folder as vault* → select `vault/`.
2. Enable the **Dataview** community plugin (Settings → Community plugins).
3. Press `Ctrl+G` — the graph shows the 15 demo skills colored by mastery
   (gray = not started, amber = familiar, green = proficient, blue = mastered).
4. Open `1 - order-of-operations.md` to see the note anatomy: frontmatter,
   sub-skill checkboxes, prerequisite links.

Play the loop:

```bash
# tick a checkbox in Obsidian, then grade the review:
python srs_fsrs.py --grade "13 - linear-inequalities.md:13a: Solve ax + b < c." Good
# log a mistake in 5 seconds:
python log_error.py 8 "forgot to multiply the outer terms"
# evening close-out (sync mastery tags, regenerate dashboards):
python evening.py
```

---

## Track B — Build your own subject

The build is designed to be executed by an AI agent (Claude Code, Cursor, or any
agent that can read files and run Python). It works manually too — every phase has a
non-AI fallback — but AI does the heavy lifting (note generation, edge mining).

**Agent route (recommended):** open the `vault/` folder with your agent and say:

> Read AGENTS.md and .claude/skills/knowledge-graph/SKILL.md. Build me a knowledge
> graph vault for <SUBJECT> from <SOURCE>. Follow the phases in
> docs/02-build-pipeline.md; keep the demo notes until my subject works, then delete them.

**Manual route:** follow `docs/02-build-pipeline.md` phase by phase.

### The five phases at a glance

| Phase | What | Effort |
|---|---|---|
| 1. Extract | Curriculum source → `{id, name, topic, domain, subskills[]}` JSON | Depends on source: syllabus PDF (easy), textbook TOC (easy), online platform (needs a scraper) |
| 2. Generate | One `.md` note per skill from the JSON, flat in vault root | Scripted, minutes |
| 3. Mine | Batched AI analysis → typed prerequisite edges → validate → apply | The core. ~30 min with 3 parallel agents for ~900 skills |
| 4. Color | `graph.json` rules: domain palette + mastery overrides | Minutes (close Obsidian first!) |
| 5. Engine | The scripts just work — they read frontmatter + the edge store | Zero: already in this repo |

### What you need to bring

- **A curriculum source.** A syllabus/spec PDF is the easiest single source of truth
  (works great for admission tests); a structured course platform is richest;
  a textbook table of contents works fine. Target shape per skill:

  ```json
  {"num": 42, "name": "Solve two-step equations", "topic": "equations",
   "domain": "Algebra", "subskills": ["42a: Solve ax + b = c", "42b: ..."]}
  ```

- **An AI agent or API access** for Phase 3 edge mining (a cheap model is fine —
  the reference build used a budget model for mining and a strong model only for QA).
- Optional: **past-paper PDFs** you have rights to, for the question-bank pipeline
  (`docs/05-paper-pipeline.md`).

### Subjects that fit (and don't)

Cumulative subjects (maths, physics, CS, chemistry, admission tests) fit best.
Essay-heavy subjects work with a SOFT-edge-heavy graph (`docs/ADAPTATION-economics.md`).
**Rule of thumb:** if >40% of mined edges come out SOFT, the subject may not reward a
prerequisite graph — use plain FSRS with topic notes instead (the SRS half of this
repo still works standalone for languages, vocabulary, and other flat domains).

### After the build

- Daily loop: `docs/04-daily-workflow.md` (morning.py → study → log_error.py → evening.py).
- Optional hourly automation: `automation/README.md`.
- Read `docs/07-pitfalls.md` **before** your first bulk edit — it is the accumulated
  scar tissue of the reference build and will save you hours.
## Optional: use the local GUI

From the `vault/` directory, run `python cockpit_app.py`. The included demo course
and original demo question bank make the Today, Study, Courses, Progress and
Settings views usable immediately. Edit `config/course_catalog.json` to define
your own course targets, route profiles and deadline. The course catalogue defines
destinations; graph ancestors stay available for causal support recommendations.
For a second subject vault, define its catalogue and run
`python automation/install_cockpit.py --vault C:\path\to\vault --port 8766`.
Subject-specific error types and assessment rubrics belong in the catalogue;
the Python cockpit files remain shared. See `docs/11-subject-adapters.md`.
