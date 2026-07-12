# 08 — Case Studies & Benchmarks

Two real builds of this system, plus the open taxonomy used as the quality benchmark.

## Case study 1 — A-Level Maths + Further Maths (the reference build)

The original vault this repo was extracted from.

- **Scale:** ~900 skill notes (each with 2–12 lettered sub-skills), 1,500+ typed
  prerequisite edges mined by AI in 26 domain batches, 57 topic MOC notes.
- **Build effort:** curriculum extraction scripted; note generation scripted;
  edge mining ~30 minutes with 3 parallel agents on a budget model; validation +
  spot-checks by a strong model.
- **Audit results** (independent validation pass): 0 cycles, 0 duplicate edges;
  open findings were 241 transitively-redundant HARD edges (~16% — transitivity
  leaks in, see pitfalls), 67 orphan notes (8%), 6 dangling edge endpoints.
  Edge mix: ~85% HARD / 13% SOFT / 2% IMPLICIT_REVIEW-explicit.
- **Engine outcomes:** flow-zone + unlock-leverage ranking replaced ad-hoc "what
  should I do today" entirely; the FSRS reseed incident (see engine internals) proved
  the value of dual bookkeeping (legacy ladder + FSRS) — the bug was caught because
  the two systems disagreed.
- **Extension:** a past-paper question bank (2,000+ questions, ~98% auto-tagged to
  graph nodes by a budget model) generating per-node practice notes and booklets.

## Case study 2 — TMUA admission test (spec-PDF source)

A second vault built from a completely different source type: the exam's official
specification PDF plus its two accompanying "Notes on..." documents.

- **Scale:** ~91 nodes, 321 sub-skills, 117 edges, 58 hand-crafted practice
  questions across 12 domains.
- **Lessons that generalize:**
  - A spec PDF is the cleanest possible Phase-1 source — the assessment points *are*
    the skill list; no scraping, no inference.
  - Admission-test graphs are small (60–120 nodes) and benefit from a dedicated
    logic/reasoning domain when the exam tests it.
  - A question bank (Phase 7) is high-value here because past papers are scarce and
    the format is distinctive — questions were hand-written to match the exam style
    and tagged to skill ids, making them servable by flow zone.
  - Validation (cycle check, dangling ids, transitive reduction) ran as an automatic
    gate after each edge batch — the graph shipped clean on the first audit.

## The benchmark — Marble Skill Taxonomy

[github.com/withmarbleapp/os-taxonomy](https://github.com/withmarbleapp/os-taxonomy)
(ODbL + CC BY-SA) is the best open example of production knowledge-graph schema
design: 1,590 micro-topics / 3,221 edges for ages ~5–11 (503 math topics).

Ideas adopted from it, worth stealing for any subject:

- **Topic `type` field** (CONCEPTUAL / PROCEDURAL / META / LANGUAGE /
  REPRESENTATIONAL) — classify skills by learning mode.
- **`evidence`** — ~3 observable "can the learner do X" criteria per topic; exactly
  what sub-skill checklists should look like (behavioral, checkable).
- **`assessmentPrompt`** — one plain question per topic to verify mastery; cheap to
  generate at note-creation time.
- **Edge fields** `{topicId, prerequisiteId, strength: hard|soft, reason}` —
  independently validates the HARD/SOFT + one-sentence-reason design.
  (Marble has no IMPLICIT_REVIEW; that's this system's FIRe extension.)
- **Healthy-graph statistics to audit against:** mean ~2.0 prerequisites per topic,
  max 9, ~6% root (zero-prereq) topics, 0 hard-edge cycles, hard:soft ≈ 63:37.

Related open references: **learning-commons-org/knowledge-graph** (US standards +
math learning components at scale), **moaaz-ae/plcourse** (the fractional-credit DAG
mechanics FIRe's chain-weighting draws on).

## Audit methodology (repeatable on any vault)

1. Load the enriched edge store; count nodes/edges/types.
2. Cycle check (DFS over HARD edges) — must be 0.
3. Duplicate edges — must be 0.
4. Transitive redundancy — % of HARD edges with an alternate 2–3 hop HARD path;
   under ~5% is clean, the reference build's 16% shows what unreduced mining leaves.
5. Dangling endpoints and orphan notes — list them; orphans <5%.
6. Compare distributions (prereqs/node, root %, hard:soft) against Marble's stats.
7. Spot-check 20 random HARD edges by hand — ≥18 defensible or re-mine that domain.
