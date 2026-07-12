# Adaptation — Economics (and other essay subjects)

Essay subjects have a *weak* prerequisite hierarchy — most concepts can be learned in
many orders. The graph still earns its keep, but differently: less gating, more
structure-for-review.

## Domains

Micro: Demand/Supply, Elasticity, Costs, Market Structures, Market Failure.
Macro: Growth, Inflation, Trade, Fiscal/Monetary Policy, Development.

## Pipeline adjustments

- **Lean on SOFT_PREREQ heavily.** Very little genuinely *gates*; most edges express
  "this is easier if you've seen that". Keep HARD for the few real gates (elasticity
  calculations genuinely need demand/supply; evaluation genuinely needs the theory
  it evaluates).
- **Separate note types**, tagged in frontmatter: `type: theory | diagram |
  calculation | evaluation`. Diagram skills (draw/shift curves, label areas) are
  distinct nodes from the theory they illustrate — they fail independently.
- **Map assessment objectives to the graph:** AO3 (evaluation) nodes depend on AO1
  (knowledge) and AO2 (application) nodes — this is where the few HARD edges live.
- **Case-study/current-events notes** link back to theory nodes as they occur; they
  are IMPLICIT_REVIEW sources, not prerequisite targets.
- **Definitions are SRS gold.** A flat definitions deck (one sub-skill per term)
  plays to FSRS's strengths; keep definitions as sub-skills of their concept note
  rather than separate nodes.

## The >40% SOFT rule

If more than ~40% of mined edges come out SOFT, the subject doesn't reward
flow-zone gating — and that's fine. Run the same vault but treat the diagnostic's
flow zone as a *suggestion list* rather than a frontier, and let FSRS + error triage
carry the load. The mastery ladder, checkbox tracking, error log, and daily wrappers
all work identically.

## Essay-specific loop

The error log becomes a **marking-feedback log**: after each marked essay, log the
lost marks (`log_error.py <node> "no evaluation of magnitude" --sev high`) and let
`/error-triage` aggregate — recurring AO3 losses across different topics are a
skill gap (an evaluation-type node), not a content gap. That distinction is the
single most useful thing the graph does for essay subjects.
