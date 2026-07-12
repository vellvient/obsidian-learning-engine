# 02 — Build Pipeline (curriculum → knowledge graph)

The six-phase pipeline that turns any curriculum source into a working vault.
This is the spine of the whole system; it is written to be executed by an AI agent
(the shipped `vault/.claude/skills/knowledge-graph` skill is the agent-facing version
of this document) but every phase has a manual fallback.

```
1 EXTRACT   curriculum source → JSON {domain, topic, id, name, subskills[]}
2 GENERATE  one .md note per skill, flat in vault root, YAML frontmatter
3 MINE      batched AI prerequisite analysis → typed edge list → VALIDATE → apply
4 AGGREGATE roll exercise edges up to topic (MOC) notes
5 COLOR     graph.json rules: mastery tags override domain colors
6 ENGINE    FSRS + flow-zone + FIRe consume the graph (already built — this repo)
```

Optional Phase 7 (question banks from past papers) is `05-paper-pipeline.md`.

---

## Phase 1 — Extract (bring your own curriculum)

Any source works: a syllabus/spec PDF, a textbook table of contents, an online course
platform, a question-bank dump. Normalize to one JSON list:

```json
[
  {
    "num": 42,
    "name": "Solving two-step equations",
    "topic": "equations",
    "domain": "Algebra",
    "subskills": [
      "42a: Solve ax + b = c",
      "42b: Solve equations with the unknown on both sides"
    ]
  }
]
```

Guidance by source type:

- **Exam-board spec / admission-test spec PDF** — the easiest single source of truth.
  Extract the numbered assessment points directly; each becomes a skill, its bullet
  points become sub-skills. Graphs from specs tend to be small (60–120 nodes) and clean.
- **Textbook** — chapters → domains, sections → topics, exercises → skills. Write
  sub-skills as *observable behaviors* ("can compute X given Y"), not chapter titles.
- **Course platform** — richest source but needs a scraper; keep the platform's own
  exercise IDs as `num` so you can cross-reference later.
- **Sub-skill quality bar** (borrowed from Marble's `evidence` field): 2–5 per skill,
  each behaviorally checkable — a thing you can test yourself on, not a vibe.

For seeding prerequisite intuition in a new subject, consult open graphs as *priors,
not gospel*: **Marble Skill Taxonomy** (withmarbleapp/os-taxonomy),
**learning-commons-org/knowledge-graph**, **moaaz-ae/plcourse**.

## Phase 2 — Generate notes

Filename: `{num} - {slug}.md`, all flat in the vault root. Frontmatter schema
(keep it identical across subjects so the scripts port unchanged):

```yaml
---
topic: equations
exercise: 42
name: "Solving two-step equations"
mastery: not-started
tags: [not-started, equations]
created: 2026-07-12
parents: ["[[Equations]]"]
prerequisites: []        # filled by Phase 3 --apply
leads-to: []             # filled by Phase 3 --apply
implicit_review: []      # optional [id, weight] pairs; defaults to prerequisites
---

#not-started

#equations
# 42: Solving two-step equations

**2 subskills**

- [ ] 42a: Solve ax + b = c.
- [ ] 42b: Solve equations with the unknown on both sides.

[[Equations]]
```

Conventions that matter (scripts depend on them):
- The body `#not-started` tag drives graph coloring (Obsidian reads body tags).
- Checkbox lines `- [ ] {id}{letter}: {name}.` are the mastery/SRS atoms.
- Slugs: lowercase, hyphens, strip punctuation, cap ~80 chars — and **freeze the
  slugify function** before any bulk generation (see `07-pitfalls.md`).
- One topic MOC note per domain (`Equations.md`), linked via `parents` + a body wikilink.

Generation is mechanical — safe to delegate to an agent or a 30-line script that
reads the Phase 1 JSON. See the demo notes in `vault/` for the exact target shape.

## Phase 3 — Mine prerequisites (the core)

Goal: for every skill, which other skills must come first (HARD), which help (SOFT),
and which get rehearsed implicitly (IMPLICIT_REVIEW).

**Batching architecture** (proven at ~900 skills / 26 batches / ~30 min with 3
parallel agents):

1. `scripts/graph_pipeline/prereq_batch_processor.py --generate` groups skills by
   domain (~40 per batch) into `.engine/prereq_mining/batch_*.json`. Each batch =
   skill data + a shared **compact master index** of ALL skills (for cross-domain
   edges) + already-known edges (to avoid duplicates).
2. `scripts/graph_pipeline/make_compact.py --input-dir .engine/prereq_mining` strips
   the duplicated master index out of each batch (190KB → 8–55KB) — essential for
   cheap-model context limits.
3. Each batch goes to an AI model with the mining rules (a reference system prompt
   ships in the skill). Cheap models are fine for this: the reference build routed
   mining to a budget model and used a strong model only for QA. Output per batch:
   `[{from, to, type, reason}]` into `.engine/prereq_mining/results/`.
4. `--merge` dedupes and merges into `.engine/prerequisite_edges.json`;
   `--apply` writes `prerequisites:` / `leads-to:` / `implicit_review:` into note
   frontmatter and adds `## Prerequisites` / `## Leads To` wikilink sections.
   **Run merge+apply after each wave**, not only at the end.

Mining rules (put these in the model prompt):
- Link by skill id, not topic. Decompose each sub-skill into the concepts it needs.
- **No transitivity:** skip A→C if A→B and B→C already exist.
- Cross-domain edges are the high-value targets.
- Don't skip skills with empty existing prerequisites — they often need foundation
  material from *other* domains.
- One-sentence reason per edge, referencing the specific sub-skill that needs it.
- Fan-in sanity: >8 HARD prereqs on one node usually means the node is too coarse.

### Validation gate (run before every --apply)

- **Cycle check** — DFS over HARD edges; any cycle is a bug (demote the weaker edge
  to SOFT or delete it).
- **Transitive reduction** — drop A→C where a 2–3 hop HARD path exists (idempotent
  script; run after each wave).
- **Dangling ids** — every `from`/`to` must match an existing note.
- **Orphans** — notes with no edges at all are usually mining misses; target <5%.
- **Edge-count sanity** — expect ~1.5–2 edges per skill. Much less = missed
  connections; much more = transitivity leaked through.
- `scripts/graph_pipeline/verify-batch-edges.py` checks result files against the
  master index before merging.

## Phase 4 — Aggregate to topics

`scripts/graph_pipeline/aggregate_topics.py` rolls exercise-level edges up to the
topic MOC notes (via each note's `parents`), writing `## Topic Prerequisites`
sections so the topic layer of the graph is connected too.

## Phase 5 — Color the graph

`.obsidian/graph.json` color groups, in priority order (Obsidian applies the FIRST
matching group, and body tags mean every note matches something):

```
#mastered (blue) > #attempted (red) > #proficient (green) > #familiar (amber)
> #not-started (gray, LAST) > domain tags (palette, after mastery)
```

**Close Obsidian before writing graph.json** — it overwrites the file from memory
within seconds if open (`07-pitfalls.md`).

## Phase 6 — Engine

Nothing to build: the scripts in this repo read frontmatter + the edge store.
Run `python scripts/verify_engine.py` — a checked build passes all engine checks —
then `python morning.py` for your first ranked study plan.

## Quality bar — when is the graph done?

- 0 cycles, 0 dangling ids, <5% orphan nodes
- Every edge has a reason
- Spot-checking 20 random HARD edges finds ≥18 you would defend
- The flow-zone query returns a sane "what next" for BOTH a beginner profile
  (all not-started) and a mid-course profile
- Benchmarks from healthy production graphs (Marble): mean ~2.0 prereqs/topic,
  max ~9, ~6% root topics, hard:soft ≈ 63:37
