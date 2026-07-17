---
name: knowledge-graph
description: Build a Math Academy-style prerequisite knowledge graph and study vault (Obsidian) for any subject — extract a curriculum into granular skill notes, mine prerequisite edges with batched AI analysis, validate the DAG, and wire up mastery tracking, FSRS spaced repetition, and FIRe implicit-review dashboards. Use when the user wants to create/extend a knowledge graph, add a new subject vault, re-mine prerequisites, or audit graph quality.
---

# Knowledge Graph Builder — Math Academy-style learning vaults

This vault IS the reference layout: the engine scripts live at its root
(`srs_fsrs.py`, `study_today.py`, `morning.py`, `evening.py`, `flow_diagnostic.py`)
and the mining pipeline in `scripts/graph_pipeline/`. Reuse them rather than
rewriting. The methodology chapter of the handbook (`../docs/02-build-pipeline.md`)
is the long-form version of this skill; the original reference build was an A-Level
maths vault (~900 notes, 1,500+ AI-mined edges).

## Case study: admission-test vault (spec-PDF source)
A second reference build (~91 nodes, 321 subskills, 117 edges, 58 practice
questions) was constructed for the TMUA admission test from the exam's official
specification PDF + its accompanying notes documents — a different source type,
with good results. See `references/tmua-vault-case-study.md` for the build log,
reusable patterns, and lessons specific to spec-PDF extraction and exam-prep
question banks.

## Design principles (what makes the graph high quality)

1. **Granularity is everything.** Nodes are *individual exercises/skills* (e.g.
   "Solve a linear inequality with brackets"), not chapters. Math Academy's edge:
   3,000+ fine-grained topics. Each note also lists lettered **subskills**
   (339a, 339b, …) — those are the units of mastery and SRS tracking.
2. **It must be a DAG.** No cycles, ever. Direction: `from` = prerequisite,
   `to` = dependent.
3. **Typed edges.**
   - `HARD_PREREQ` — must be known first (gates the flow zone)
   - `SOFT_PREREQ` — helpful, not gating
   - `IMPLICIT_REVIEW` — practicing the dependent skill naturally rehearses this
     prerequisite (powers FIRe fractional credit: review old stuff by learning new stuff)
4. **Transitive reduction.** Never add A→C when A→B→C exists. Redundant edges
   dilute unlock-priority and FIRe computations.
5. **Cross-domain edges matter most.** Algebra inside geometry, stats inside
   mechanics — these are the edges naive per-chapter mining misses.
6. **Every edge carries a one-sentence reason.** Unreviewable edges rot.
7. **Mastery lives on the node** (`not-started → attempted → familiar →
   proficient → mastered`) and drives everything downstream: flow zone =
   skills whose HARD_PREREQs are all proficient/mastered; unlock leverage =
   how many skills this node is the sole missing prereq of.

## Pipeline (6 phases)

```
1 EXTRACT   curriculum source → JSON {topic, unit, id, name, subskills[]}
2 GENERATE  one .md note per skill, flat in vault root, YAML frontmatter
3 MINE      batched AI prerequisite analysis → typed edge list
4 AGGREGATE roll exercise edges up to topic (MOC) notes
5 COLOR     Obsidian graph.json rules: mastery tags override domain colors
6 ENGINE    FSRS + flow-zone diagnostic + FIRe dashboards consume the graph
```

### Phase 1 — Extract
Any source works (DrFrost, Khan, a textbook TOC, a syllabus PDF). Normalize to
`{domain, topic, id, name, subskills[]}`. For seeding prerequisite structure in
new subjects, consult open graphs: **Marble Skill Taxonomy** (see below),
**learning-commons-org/knowledge-graph** (US standards + math learning
components), **moaaz-ae/plcourse** (fractional-credit DAG mechanics). Use them as
*priors*, not gospel — handcraft-verify anything they assert.

#### Marble Skill Taxonomy reference (github.com/withmarbleapp/os-taxonomy)
The best open example of production KG schema design. 1,590 micro-topics
(503 math, ages ~5-11) / 3,221 edges, ODbL + CC BY-SA licensed. Data files:
`topics.json`, `dependencies.json`, `clusters.json`, `curriculum-standards.json`,
with JSON Schemas in `schema/`. Ideas worth stealing:
- **Topic `type` field**: CONCEPTUAL / PROCEDURAL / META / LANGUAGE /
  REPRESENTATIONAL — same idea as the math vault's five learning modes.
- **`evidence`**: ~3 observable "can the learner do X" criteria per topic —
  exactly what subskill checklists should look like (behavioral, checkable).
- **`assessmentPrompt`**: one plain-language question to verify mastery —
  cheap to generate at note-creation time, useful for self-testing.
- **Precomputed `centrality`** per node: used to rank search results and
  frontier picks — equivalent to the vault's unlock-leverage score.
- **Edge fields**: `{topicId, prerequisiteId, strength: hard|soft, reason}` —
  validates the vault's HARD/SOFT + one-sentence-reason design (Marble has no
  IMPLICIT_REVIEW; that is the vault's FIRe extension).
- **Healthy stats to benchmark against**: mean ~2.0 prereqs/topic, max 9,
  ~6% root (zero-prereq) topics, 0 hard-edge cycles, hard:soft ≈ 63:37.

### Phase 2 — Generate notes
Filename: `{id} - {name}.md`. Frontmatter schema (keep identical across subjects
so the scripts port unchanged):

```yaml
---
num: 339
name: "Solving linear inequalities in one variable"
topic: algebra
domain: Algebra           # same as domain tag, used by engine scripts
tags: [algebra, not-started]
mastery: not-started
prerequisites: []         # filled by --apply
leads-to: []              # filled by --apply
implicit_review: []       # optional [id, weight] pairs, default weight 0.3
parents: ["[[Topic MOC note]]"]
---
## Subskills
- [ ] 339a: ...
```

### Phase 3 — Mine prerequisites (the core)
Batch by domain, ~40 skills per batch. Each batch JSON = skill data + a shared
*compact master index* of ALL skills (for cross-domain edges) + already-known
edges (to avoid duplicates). Analyse each batch (subagents for big batches,
inline for <15 skills) with the mining rules above; output
`[{from, to, type, reason}]`. Then merge → dedupe → **validate** → apply to
frontmatter. Mining rules for the system prompt: link by skill id, decompose
subskills into needed concepts, no transitivity, cross-domain edges are the
high-value targets, one-sentence reason per edge (see
`../docs/02-build-pipeline.md` Phase 3 for the full rule list).

Operational lessons from the math build: strip the master index out of each
batch file (190KB → 8-55KB); run merge+apply after each wave, not only at the
end; re-dispatch subagents silent for ~5 min.

### Validation gate (run before --apply, every time)
- **Cycle check**: DFS over HARD_PREREQ edges; any cycle is a bug — break it by
  demoting the weaker edge to SOFT_PREREQ or deleting it.
- **Transitive reduction**: drop A→C where a 2-3 hop HARD path A→…→C exists.
  An automatic reduction script (`transitive_reduce.py`, example in the TMUA vault)
  can be run idempotently after each edge batch to keep the graph clean.
- **Dangling ids**: every `from`/`to` must match an existing note id.
- **Orphans**: flag notes with no edges at all — usually a mining miss.
- **Fan-in sanity**: >8 HARD_PREREQs on one node usually means the node is too
  coarse — consider splitting it.

### Phases 4-6 — Aggregate, color, engine
Aggregate edges to topic MOC notes (`aggregate_topics.py`). Color the graph:
domain tag palette at low priority, then `not-started` gray / `struggling` red /
`familiar` yellow / `mastered` green on top, so mastery always wins visually.
Then port the engine scripts and point them at the new vault: FSRS scheduling
(`srs_fsrs.py`), daily ranked picks (`study_today.py` = flow zone × unlock
leverage), morning/evening entrypoints, error capture (`log_error.py`) and the
`/error-triage` skill.

### Phase 7 (optional) — Question bank generation
For exam-prep vaults (TMUA, MAT, STEP, SAT, etc.), generate a bank of practice
questions tied to skill IDs. Each question is a dict with `{id, skills[],
domain, paper, stem, options[5], answer, explanation}`. The TMUA vault's
`scripts/tmua_questions.py` demonstrates this pattern: 58 questions across 12
domains, filterable by topic/paper/skill, in compact CLI format or markdown.
Questions are hand-crafted to match the target exam's format (multiple choice,
no-calculator traps, thinking-over-writing style).

## Subject adaptation notes
- **Physics**: deeper chains (Forces → Energy → SHM), more cross-domain edges,
  add practicals as a distinct node type.
- **Economics / essay subjects**: hierarchy is weak — lean on SOFT_PREREQ;
  separate note types for definitions, diagrams, and evaluation skills.
- **University admission tests (TMUA, MAT, STEP, BMAT)**: test a fixed syllabus
  (spec PDF from the exam board). Extract topics directly from the specification
  document — it is the single source of truth. The graph tends to be smaller
  (60–120 nodes) and should include a dedicated logic/reasoning domain if tested.
  An optional Phase 7 (question bank generation) adds high value here because
  past papers are scarce and the exam format is distinctive (no calculator,
  multiple choice, thinking speed).
- Anything non-cumulative: if >40% of edges come out SOFT, the subject may not
  reward a prerequisite graph; consider plain SRS instead.

## Quality bar
A graph is done when: 0 cycles, 0 dangling ids, <5% orphan nodes, every edge has
a reason, spot-checking 20 random HARD edges finds ≥18 you'd defend, and the
flow-zone query returns a sane "what to study next" for a beginner profile
(all-not-started) AND a mid-course profile.
