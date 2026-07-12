# Adaptation — Physics (and other deep-chain sciences)

Physics fits the prerequisite-graph model extremely well — arguably better than
maths, because the dependency chains are deeper and cheating them hurts more.

## Domains

Mechanics · Electricity · Waves · Particles · Thermal · Fields · Nuclear · Practical
(adjust to your syllabus's own groupings — the exam board's topic list is the source
of truth).

## Pipeline adjustments

- **Chains are deep.** Forces → Work/Energy → SHM → Damping is four HARD hops; the
  flow zone gates hard, which is correct. Expect fewer entry points than maths.
- **Cross-domain edges matter even more.** Mechanics inside fields, waves inside
  quantum, thermal inside nuclear — and *maths inside everything* (vectors,
  logarithms, exponentials, trig). If you maintain a maths vault too, keep the
  subjects in separate vaults but mirror the needed maths skills as nodes with a
  `type: external` marker, or accept SOFT edges to concepts you track elsewhere.
- **Practicals are a distinct node type.** Add `type: practical` in frontmatter for
  required practicals/lab skills; they have prerequisite edges *into* theory nodes
  (you need the theory to interpret the practical) and are natural IMPLICIT_REVIEW
  sources (doing a practical rehearses several theory nodes at once — set explicit
  `implicit_review` weights).
- **An equations-sheet reference note** linked from relevant skill notes works well;
  don't make each equation its own node (too granular even for this system — the
  *skill of using* the equation is the node).

## Sub-skill style

Physics sub-skills should separate the three things that fail independently:

```
- [ ] 63a: State the conditions for simple harmonic motion.
- [ ] 63b: Derive a = -w^2 x for a given system.
- [ ] 63c: Calculate period/frequency from graph or equation data.
- [ ] 63d: Sketch displacement/velocity/acceleration against time.
```

(definition · derivation · calculation · representation — the same skill "knowing
SHM" hides four different mastery states.)

## Past papers

The paper pipeline works unchanged for physics papers; expect `has_figure` on most
questions (circuit diagrams, field sketches) — which is exactly why questions are
served as PDF renders rather than extracted text. Multiple-choice components make
good micro-trainer material rather than practice-note material.
