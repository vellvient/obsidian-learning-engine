# Obsidian Learning Engine

A self-hosted, Math Academy-style learning system built on Obsidian + plain Python.
Model any subject as a **prerequisite knowledge graph**, track mastery per sub-skill,
schedule reviews with **FSRS**, get implicit review credit through the graph (**FIRe**),
and let a daily **flow-zone** ranker tell you exactly what to study next.

Built and battle-tested on a real A-Level Maths + Further Maths vault
(~900 notes, 1,500+ AI-mined prerequisite edges), then generalized so anyone —
human or AI agent — can replicate it for any subject.

## What you get

1. **Knowledge graph** — one note per skill, lettered sub-skill checkboxes, typed
   prerequisite edges (`HARD_PREREQ` / `SOFT_PREREQ` / `IMPLICIT_REVIEW`), colored
   Obsidian graph where mastery always wins visually.
2. **Flow-zone diagnostic** — daily report of what is *just-right difficulty*:
   skills whose hard prerequisites you know but which you haven't mastered.
3. **FSRS v6 + chain-weighted FIRe** — modern spaced repetition, zero dependencies,
   plus fractional implicit review: practicing a skill boosts the stability of its
   prerequisite ancestors, so you review old material by learning new material.
4. **Error capture + triage** — log a mistake in ~5 seconds mid-session; batch-analyse
   with an AI agent later (classify, root-cause via the graph, update weak spots).
5. **Micro-schema fluency trainer** — CCT-style timed drills for automaticity,
   bridged to the graph so the daily plan suggests the right drills.
6. **Past-paper pipeline** (optional) — turn a folder of exam PDFs into a topic-tagged
   question bank: per-node practice notes with rendered question images, folded answers,
   and printable booklets. Bring your own PDFs; the pipeline is subject-agnostic.

## Quickstart (5 minutes)

```bash
git clone https://github.com/vellvient/obsidian-learning-engine
cd obsidian-learning-engine/vault
python morning.py        # ranked study plan from the demo data
python study_today.py    # the flow-zone x unlock-leverage ranker on its own
python srs_fsrs.py --due # what FSRS says is due
```

Open the `vault/` folder in Obsidian (install the **Dataview** community plugin when
prompted) and press `Ctrl+G` for the colored graph. The vault ships with a 15-note
"Algebra Basics" demo — real edges, real SRS state — so every script runs out of the box.

**The core engine is pure Python standard library.** No pip installs, no accounts,
no cloud. (Only the optional past-paper pipeline needs `pip install pymupdf`.)

To build your own subject, see [GETTING_STARTED.md](GETTING_STARTED.md).

## How it fits together

```
curriculum source ──extract──▶ skill notes (one .md per skill, checkbox subskills)
                                    │
                     AI batch mining▼
                    prerequisite edges (.engine/prerequisite_edges.json)
                                    │
        ┌────────────┬──────────────┼───────────────┬─────────────┐
        ▼            ▼              ▼               ▼             ▼
   graph colors   flow-zone     FSRS + FIRe     unlock-      practice
   (Obsidian)     diagnostic    scheduling      leverage     material
                       └────────────┴───────────────┘
                                    ▼
                         study_today.py / morning.py
                       "here is exactly what to study"
```

## Repository layout

```
docs/            the full handbook (architecture → build pipeline → engine → pitfalls)
vault/           the template vault — open this in Obsidian; scripts live inside it
automation/      optional hourly SRS watcher + scheduler setup
```

Start with `docs/01-architecture.md`, or just hand `vault/AGENTS.md` to your AI agent.
Ideas on the roadmap (and honest analyses of rejected ones, like two-way Anki sync):
[FUTURE_IMPROVEMENTS.md](FUTURE_IMPROVEMENTS.md).

## Design lineage & attribution

- **FSRS** — the scheduler is a from-scratch port of FSRS v6 by the
  [open-spaced-repetition](https://github.com/open-spaced-repetition) project (Jarrett Ye et al.).
- **FIRe (Fractional Implicit Repetition)** — concept from
  [Math Academy](https://www.mathacademy.com) / Justin Skycak's writing on their
  learning engine. This project is *inspired by* Math Academy and is **not affiliated
  with it**; the chain-weighted implementation here also draws on the open
  `plcourse` fractional-credit DAG design.
- **Marble Skill Taxonomy** ([withmarbleapp/os-taxonomy](https://github.com/withmarbleapp/os-taxonomy),
  ODbL/CC BY-SA) — used as the schema benchmark for what a healthy production
  knowledge graph looks like (see `docs/08-case-studies.md`).

## Content policy

This repo contains **no copyrighted curriculum or exam content** — no exam-board
questions, no scraped course data. The demo vault is original toy content. The
past-paper pipeline is code only: you point it at PDFs you have the right to use.

## License

MIT — see [LICENSE](LICENSE).
