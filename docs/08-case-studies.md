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
- **Extension:** a 4,797-question CIE 9709/9231 bank (~98% auto-tagged to graph
  nodes by a budget model), with 4,753 original mark-scheme crops, LaTeX final
  answers, 414 per-node practice notes/booklets, and an FSRS/error-log-aware
  interactive serving loop.

## Case study 2 — TMUA admission test (spec-PDF source)

A second vault built from a completely different source type: the exam's official
specification PDF plus its two accompanying "Notes on..." documents.

- **Scale:** ~91 nodes, 321 sub-skills, 117 edges, **315 official past-paper questions** (2017–2023 + specimen) tagged to 74 nodes, plus 58 supplementary hand-crafted questions.
- **Unified result:** the 91 TMUA objectives were mapped onto 196 canonical
  A-Level maths nodes. Ten genuinely distinct logic/proof skills became new
  nodes and 13 hard bridge edges joined them to the existing proof graph. The
  315 official questions then generated topical practice on 155 canonical nodes.
- **Lessons that generalize:**
  - A spec PDF is the cleanest possible Phase-1 source — the assessment points *are*
    the skill list; no scraping, no inference.
  - Admission-test graphs are small (60–120 nodes) and benefit from a dedicated
    logic/reasoning domain when the exam tests it.
  - A question bank (Phase 7) is high-value here. Preserve original question and worked-solution crops, use extracted text only for topic tagging, and serve questions by flow zone; hand-crafted questions remain supplementary.
  - When an admission test overlaps a larger subject graph, use a **course
    overlay**, not a second copy of every concept. Shared maths skills should have
    one node and one mastery state; course tags select TMUA/9709/9231 views, while
    TMUA-only logic, proof, and test-strategy nodes extend the shared DAG. Import
    question tags through an explicit old-id → canonical-id map.
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

### Reproduce the TMUA corpus

The template ships `vault/scripts/tmua_pipeline.py` and `vault/tmua_quiz.py`. Supply your own legally obtained official PDFs; no exam content is included:

```powershell
$env:TMUA_PDF_DIR = "C:\path\to\TMUA_PDFs"
cd vault
python scripts/tmua_pipeline.py --extract --render --batches
# Process .engine/paper_mining/batch_*.json with your chosen agent CLI.
python scripts/tmua_pipeline.py --merge --practice
python tmua_quiz.py --paper 2 --count 10
```

Expected filenames are `{year}_TMUA_Paper1.pdf`, `{year}_TMUA_Paper2.pdf`, a combined `{year}_TMUA_AnswerKey.pdf`, and matching `*_WorkedAnswers.pdf`. The extractor also accepts the early-specimen naming variant used by UAT-UK archives.
