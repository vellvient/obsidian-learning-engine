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

## Verified operating loop

Guided study serves up to 15 due FSRS reviews, then questions associated with
the ranked prerequisite-ready plan. Each wrong or partial answer needs an error
type and one useful sentence. A vague first concept failure produces a short
target-learning pause, not an arbitrary ancestor. Named intermediate-step
evidence, explicit prerequisite evidence, or repetition can launch a diagnostic.

If the diagnostic fails, the learner receives a 10–20 minute repair pause and
then fresh support questions where available. Passing returns to the original
target; misses are retried after two intervening questions. Empty timed sessions
are discarded. Session summaries count correct, partial, wrong and skipped
questions consistently, and interrupted sessions reopen directly in Study.

Finishing a non-empty session performs a safe visual refresh: checkbox-derived
mastery tags are synchronized and the Flow Zone, Review Grader, and SRS Tracker
notes are regenerated. Existing Obsidian color rules then update the graph.
The refresh never rewrites `graph.json` and does not apply FIRe; a failed
refresh does not roll back the saved session and can be retried with
`python evening.py`.

The reference test suite covers idempotency, target/support separation, causal
evidence thresholds, repair/retest/return, ranked queues, session recovery,
timed scoring and legacy empty-set filtering.

## Subject adapters

The same cockpit can serve cumulative STEM subjects, practical disciplines, and
essay subjects. `config/course_catalog.json` supplies the subject vocabulary:
course targets and routes, question-bank/render paths, learner-facing error
types, which errors constitute causal evidence, and optional rubrics selected by
component type or assessment tags. Rubric percentages provide timed evidence
without replacing source mark schemes. See `11-subject-adapters.md`.

## Local/private state

Do not publish `papers/cockpit_state.json`, question or answer renders, quiz
history, FSRS history or personal error logs. Public repositories should contain
the engine, schemas, templates and synthetic test fixtures only.
