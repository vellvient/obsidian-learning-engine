# TMUA Vault Case Study — Building from exam specification PDF

**Vault**: a sibling vault built alongside the maths reference vault  
**Subject**: Test of Mathematics for University Admission (TMUA)  
**Size**: 91 skill nodes, 321 subskills, 117 prerequisite edges, 58 practice questions  
**Source**: UAT-UK official specification PDF + Notes on Mathematics (PDF) + Notes on Logic and Proof (PDF)

---

## What's different from the math vault

| Aspect | Math Vault (DrFrost) | TMUA Vault (Spec PDF) |
|--------|---------------------|----------------------|
| Source | DrFrost exercise IDs + syllabus | Single 17-page spec PDF + 2 official guide PDFs |
| Skill count | ~850 | 91 |
| IDs | 4-digit DrFrost codes | Sequential 1-136 |
| Edge mining | Batch AI analysis (subagents) | Manual from spec reading (spec explicitly states dependencies) |
| Paper split | N/A | Paper 1 (application) vs Paper 2 (reasoning) |
| Question bank | Not generated | 58 MCQ tied to skill IDs |

## Phase 1 — Extract from spec PDF

The official UAT-UK spec PDF (3.4MB, 17 pages at `esat-tmua.ac.uk`) lists topics in
a hierarchical outline (MM1.1, MM1.2, …, M7.7). Two companion PDFs — Notes on
Mathematics (2.6MB, ~4,300 lines) and Notes on Logic and Proof (1.5MB, ~1,450
lines) — provide worked examples and deeper explanations.

**Extraction approach**: Download all 3 PDFs via `curl`, convert with `pdftotext`,
then read the plain text to identify every sub-topic. The spec gave ~68 numbered
sub-items; each was split into 1–4 granular skills depending on scope (e.g.,
MM4.6 "Trigonometric equations" → 2 skills: basic equations + equations with
compound arguments).

**Normalised output**: `{id, topic, domain, name, subskills[], prerequisites[], leads_to[]}`

## Phase 2 — Generate notes

Python generator at `.engine/TMUA_SKILL_TREE.py`. Key lessons:
- The frontmatter **must** include a `domain:` field (alongside `topic:`, both are
  consumed by engine scripts). The first build missed this — caught by validation.
- Filenames must sanitise special characters (`:`, `/`, `?`, `"`) for Windows.
- After generation, run `transitive_reduce.py` to remove redundant edges (the
  generator creates both direct edges and transitive chains).

## Phase 3 — Mine edges (manual from spec)

Unlike the math vault (which uses batch AI mining with a reference system prompt),
the TMUA spec explicitly states prerequisite ordering within each module. For
cross-domain edges, the Notes on Mathematics frequently connects topics (e.g.,
"completing the square is used in circle equations"). No AI mining was needed.

**Edge types used**: Only HARD_PREREQ (the spec is strictly cumulative). SOFT_PREREQ
and IMPLICIT_REVIEW are placeholders for future refinement.

## Phase 4 — Validate DAG

Script at `.engine/validate_graph.py`. Checks:
- 0 cycles, 0 dangling IDs, 0 orphans, 0 transitively redundant edges
- Fan-in ≤ 8 per node
- Prerequisites ↔ leads-to parity (every edge should appear in both directions)

Target benchmarks (from Marble Taxonomy): ~2.0 mean prereqs/node, ~6% roots.
TMUA vault achieved: 1.3 mean, 3.3% roots — slightly under because the GCSE
content is flatter (many nodes share few common prerequisites).

## Phase 6 — Engine (study planner)

`scripts/study_today.py` implements:
- Flow zone: skills whose HARD_PREREQs are all proficient+
- Unlock leverage: count of dependents blocked solely by this skill
- Paper emphasis filters: Paper 1 (Algebra, Calculus, Graphs, Geometry) vs
  Paper 2 (Logic and Proof)

No FSRS was ported — TMUA is test-prep with a defined exam date, not long-term
knowledge building. FSRS can be added later if desired.

## Phase 7 — Question bank

`scripts/tmua_questions.py` — 58 TMUA-style MCQs (5 options, no calculator).
Each question carries a `skills[]` field linking it to 1-3 skill IDs.
Output formats: compact CLI, markdown, or full bank file.

**Question design rules for TMUA-style:**
- 5 options labelled A-E, exactly one correct
- No calculator required — mental arithmetic or algebraic manipulation only
- Stem should be scannable in <15 seconds (TMUA: 75 min for 20 Qs = 3.75 min/Q)
- Wrong answers should be plausible (distractors from common mistakes)
- Explanation should state the key reasoning step, not just the answer
- Paper 2 questions must test reasoning (converse/contrapositive, necessity/sufficiency,
  error identification, proof structure) not calculation

## Reusable scripts

| File | Purpose | Reuse potential |
|------|---------|-----------------|
| `.engine/TMUA_SKILL_TREE.py` | Full skill tree definition + note generator | Modify `SKILLS` list for any subject |
| `.engine/validate_graph.py` | DAG validation gate | Drop into any vault |
| `.engine/transitive_reduce.py` | Auto-removes A→C when A→B→C | Run after batch edge insertion |
| `scripts/study_today.py` | Flow zone + unlock leverage planner | Port to any vault with same YAML schema |
| `scripts/tmua_questions.py` | MCQ question bank with filters | Template for any exam with MCQ format |
| `morning.py` | Daily entrypoint | Generic study session starter |

## Hard constraints from this build
- The `domain:` field is required in frontmatter (engine scripts depend on it) but
  was omitted in the first generator version — add it explicitly.
- Console codepage cp932: print non-ASCII fails. Escape `£`, `π`, superscripts,
  or set `sys.stdout.reconfigure(errors="replace")`.
- Never regenerate notes while Obsidian is open (races on file reads).
- Transitive reduction is idempotent — safe to run after every edge change.
