# Learning Cockpit

The Learning Cockpit is a dependency-free localhost web layer for the Obsidian
Learning Engine. It combines deadline planning, target/support/enrichment graph
layers, FSRS reviews, tagged-question practice, error capture and explainable
prerequisite remediation.

Run `python cockpit_app.py` from the vault root. See
`LEARNING_COCKPIT_WALKTHROUGH.md` for the learner workflow.

## Portable design

A new subject needs:

1. Granular skill notes using the standard frontmatter and subskill schema.
2. A validated HARD/SOFT prerequisite DAG.
3. A course catalogue identifying target nodes and optional routes.
4. Optional tagged question banks and render adapters.
5. Subject-specific evidence thresholds if the default mastery gate is unsuitable.

The course catalogue defines destinations. All graph ancestors remain eligible
as support nodes, so foundational gaps can be repaired without polluting formal
syllabus coverage. Multiple courses can share the same graph and mastery state.

`config/causal_bridges.json` holds reviewable SOFT support relationships that
are useful for diagnosis but should not gate the canonical flow-zone DAG. For
example, a numeracy skill can support a physics calculation without becoming a
formal physics-course coverage target.

## Local/private state

Do not publish `papers/cockpit_state.json`, question or answer renders, quiz
history, FSRS history or personal error logs. Public repositories should contain
the engine, schemas, templates and synthetic test fixtures only.
