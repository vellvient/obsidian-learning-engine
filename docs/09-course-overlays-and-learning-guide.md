# 09 — Course Overlays and the High-Speed Learning Loop

## One graph, many courses

If two courses share a concept, do not build two mastery nodes. Keep one
canonical skill and attach both course objectives and question banks to it.

Example:

```text
9709 objective ─┐
9231 objective ─┼─> canonical node: completing the square ─> one FSRS state
TMUA objective ─┘                                      └─> all question sources
```

Only course-specific skills—such as a test's special logic notation—become new
canonical nodes. This makes transfer real: work completed for one course changes
readiness in every related course.

### Mapping schema

Copy `vault/config/course_map.example.json`. Every source objective maps to:

- one canonical ID when the scopes are genuinely equivalent;
- several IDs when the source objective bundles multiple micro-skills;
- one newly allocated ID when no existing node covers it.

Validate before importing:

```bash
cd vault
python scripts/validate_course_map.py config/my_course_map.json
```

For a complete source inventory, export its objective IDs as a JSON array and add
`--source-ids source_ids.json`; the validator then rejects missing or extra rows.

### Conservative mapping rules

1. Compare observable subskills, not titles alone.
2. Never merge merely related concepts.
3. Prefer a multi-node objective over one overly broad canonical node.
4. Preserve granular reasoning/proof distinctions.
5. Retag questions to canonical IDs but retain their original source IDs for audit.
6. A question related to several nodes grades only the node selected for that attempt.
7. Validate the hard-edge DAG after adding course-specific nodes.

## The daily loop

### 1. Retrieve due material (10–20 minutes)

Produce the answer before revealing it. Grade the retrieval, not familiarity:

- Again: failed or used an invalid method;
- Hard: correct but fragile or heavily effortful;
- Good: independent and normally fluent;
- Easy: immediate and precise.

### 2. Learn one high-leverage flow-zone skill (20–40 minutes)

Select a skill whose hard prerequisites are mastered and which unlocks useful
dependents. Use worked examples briefly:

1. explain one complete example;
2. finish a partially worked example;
3. solve two varied examples unaided;
4. state the cue that tells you which method applies.

### 3. Retrieve through authentic questions (20–40 minutes)

Use `quiz.py` or the subject's serving layer. Attempt first, reveal later, then
self-grade. Original exam questions and official mark schemes are preferable to
generated exercises; generated material should fill genuine coverage gaps.

### 4. Capture errors quickly

Immediately confirm the correct method, write one sentence describing the failure,
and retry from a blank start. Defer deep AI/root-cause analysis until the end of the
session. This combines short feedback latency with low interruption cost.

### 5. Close and schedule

Run the evening workflow, update mastery from evidence, and decide tomorrow's
first task before stopping.

## What produces learning speed

- **Prerequisite repair:** fix the smallest upstream gap rather than repeating the
  whole chapter.
- **Unlock leverage:** prefer a skill that opens several useful dependents.
- **Fast support fading:** worked example -> completion -> independent -> mixed.
- **Generative effort:** predict, derive, draw, or estimate before reading.
- **Immediate correctness feedback:** never preserve a wrong method overnight.
- **Batch deep diagnosis:** do not turn each mistake into a long interruption.
- **Method-selection practice:** interleave neighbouring techniques after initial
  blocked practice establishes each one.
- **Transfer metrics:** measure unseen accuracy, repeated errors, latency, delayed
  retention, and unlocked nodes—not videos watched or pages highlighted.

## What produces retention

1. Retrieve before reviewing.
2. Space successful recalls; repeat failures sooner.
3. Test after delays, not only immediately after study.
4. Mix methods once each is independently understood.
5. Revisit an error with a fresh problem.
6. Explain the discriminating cue and key invariant.
7. Use FIRe/implicit review to avoid duplicate work, while directly reviewing
   isolated knowledge that no later skill naturally rehearses.
8. Protect sleep and recovery; exhaustion is not productive difficulty.

## Mastery is evidence

Use the ladder `not-started -> attempted -> familiar -> proficient -> mastered`.

- Familiar: solves a standard example with effort.
- Proficient: succeeds independently across normal variations.
- Mastered: remains reliable after spacing and in mixed/exam conditions.

Require method recognition, independent execution, explanation of the key step,
varied success, and a later spaced success. Finishing a lesson is not mastery.

## Weekly audit

- clear every unanalysed error;
- find recurring error types and prerequisite gaps;
- run one timed mixed set or full paper;
- compare performance by canonical node and course;
- inspect blocked/stalled nodes and the true FSRS backlog;
- choose the next two leverage bottlenecks;
- verify the graph and generated artifacts after any bulk change.

## Adapting beyond mathematics

Keep the graph/FSRS/error engine; change the retrieval object:

- physics: numerical problems, derivations, diagrams, practical decisions;
- economics/history: definitions, diagrams, data response, argument plans, evaluation;
- languages: sentence production, listening discrimination, pronunciation, contextual vocabulary;
- programming: prediction, debugging, implementation, tests, and code review.

If a subject is weakly cumulative and produces mostly soft edges, use a smaller
graph and rely more heavily on plain spaced retrieval.
