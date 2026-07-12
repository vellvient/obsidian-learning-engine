# Future Improvements

Ideas that could significantly boost learning speed, with honest caveats.
Each entry: what it is, why it should help, a rough design, and what to watch out
for. Roughly ordered by expected impact-per-effort. PRs and experiments welcome —
if you build one, keep the vault the single source of truth (see the Anki entry
for why that rule exists).

---

## 1. One-way Anki exporter (mobile dead-time reviews)

**What:** `anki_export.py` — generate an `.apkg` (via `genanki`) or push through
AnkiConnect: (a) the *rehearsable rules* that `/error-triage` prescribes for your
logged mistakes, as cloze cards; (b) flat formula/definition decks (exact trig
values, derivative tables, subject definitions). One direction only: vault → Anki.

**Why it helps:** your own error patterns are the highest-value flashcards that
exist, and Anki's mobile app turns queue time into review time. Definition-heavy
subjects (sciences, economics, languages) get a proper mobile surface.

**Why one-way — the full verdict (learned the hard way in design review):**
- Anki's modern scheduler *is* FSRS — the same algorithm this engine already runs.
  Full integration gains zero scheduling quality; it only moves the UI.
- The engine's real advantages are graph-aware and **cannot live inside Anki**:
  FIRe (practicing a skill implicitly credits its prerequisite ancestors, shrinking
  the review load), relearning-lock (a failed prerequisite hides its dependents),
  and the retrieval-proof mastery gate feeding the flow zone.
- Two-way sync means two sources of truth for "what's due". With reviews happening
  in Anki, FIRe boosts are invisible to it — Anki keeps demanding reviews the graph
  already credited, *increasing* total workload. Scheduler-state drift is this
  system's historically worst failure mode (see the reseed incident in
  `docs/03-engine-internals.md`).

**Design:** export cards tagged with their vault node id; never import review logs
back; treat the Anki deck as disposable (regenerate any time).

## 2. Examiner-report mining

**What:** exam boards publish examiner reports — professionally written analyses of
what candidates got wrong, per question, per session. Extract recurring complaints
per topic and seed `00 - Weak Spots Priority.md` *pre-emptively*.

**Why it helps:** it's a free, expert-curated catalogue of the mistakes you are
statistically likely to make, available *before* you make them. Feeding it into the
weak-spot ranking turns the error-triage loop proactive.

**Design:** PDF-extract report text → cheap-LLM pass tags each complaint with graph
node ids + a one-line "rehearsable rule" → append to weak spots with an
`examiner` source tag. Reuse the paper pipeline's batching pattern verbatim.

**Caveat:** reports describe the median candidate; calibrate against your own error
log rather than treating every warning as your weakness.

## 3. LLM-as-marker loop (remove self-marking from the quiz)

**What:** photograph your written working; a model marks it against the question's
`markscheme_points`, assigns method/accuracy marks, and auto-logs errors with the
failed step identified.

**Why it helps:** self-marking is the weakest link in any self-teaching loop — slow,
biased, and skipped when tired. Automating it makes every practice question a
graded data point.

**Design:** `quiz.py --photo` mode: after attempt, snap → vision model receives the
question, mark scheme, and your working → returns per-mark verdicts → miss ⇒
`log_error.py` with the specific failed subskill. Needs a vision-capable model;
mark schemes are already per-question in the bank.

**Caveat:** validate against ~20 hand-marked samples before trusting it; "show
that" questions and sketch questions mark poorly.

## 4. Spaced *practice*, not just spaced recall

**What:** schedule bank *questions* through FSRS, not only subskills. The quiz log
becomes a review-state store: a question type you struggled with resurfaces in
days; one you aced resurfaces in months (or never — the pool is large).

**Why it helps:** recall of a fact and fluency at a question *type* decay
differently. Interleaved, spaced problem-solving practice has stronger evidence
behind it than almost any other intervention (Rohrer & Taylor's interleaving work).

**Design:** give each (node, difficulty-band) pair an FSRS card graded by quiz
results; `quiz.py` picks due bands first. Add `--exam` mode: full-paper timed
simulation with mark-rate tracking per topic.

## 5. Difficulty auto-calibration

**What:** replace the tagging model's static easy/medium/hard guess with difficulty
re-estimated from actual user error rates in the quiz log (a one-parameter IRT-ish
update is plenty).

**Why it helps:** "just-right difficulty" is the whole flow-zone thesis; measured
difficulty beats guessed difficulty, and it personalizes over time.

**Caveat:** needs volume — keep the model's guess as the prior and shift only after
~5+ attempts per question class.

## 6. Essay-subject serving layer

**What:** the essay-subject counterpart of the paper pipeline
(see `docs/ADAPTATION-economics.md` for the graph side):
- **Marked-essay feedback loop** — after each marked essay, log lost marks per
  assessment-objective node (`log_error.py <AO3-node> "no evaluation of magnitude"`);
  triage aggregates: recurring AO3 losses across topics = a *skill* gap, not a
  content gap.
- **LLM marking against level descriptors** — boards publish level descriptors per
  band; a model can place a paragraph in a band and say what the next band needs.
- **Model-answer comparison** — diff your essay plan against a model answer's
  point structure (points made / missed / undeveloped).
- **AO3 evaluation drills** — micro-trainer-style: given a policy claim, produce
  2 evaluation angles in 90 seconds.

**Caveat:** LLM essay marking is calibration-sensitive — anchor with a few
officially-marked scripts and check agreement before trusting trends.

## 7. Auto-generated micro-schemas from error clusters

**What:** cluster error-log entries (same node, same error type); when a
procedural-bug cluster crosses a threshold, generate a new timed drill schema for
the micro-trainer automatically.

**Why it helps:** closes the last open loop: mistakes currently update *priorities*;
this makes them generate *training material*.

**Design:** `/error-triage` already classifies errors; add a step that emits a
`SchemaConfig` (the trainer is config-driven) with generated items mimicking the
failed pattern. Human-review the generated items before first use.

## 8. Per-node retention analytics

**What:** a dashboard of FSRS stability/lapse trends per topic subtree: which
domains hold, which leak, where relearning-lock fires repeatedly.

**Why it helps:** at hundreds of cards, aggregate signal beats card-level signal —
a "leaky subtree" usually means a missing prerequisite edge or a too-coarse node,
both fixable structurally rather than by grinding reviews.

**Design:** read-only script over `srs_state.json` + the graph → markdown dashboard
with per-domain stability distributions and a "structural suspects" list.

## 9. Marble-style assessment prompts per node

**What:** generate one plain-language self-test question (`assessmentPrompt`) per
node at note-creation time, following the Marble Skill Taxonomy's pattern.

**Why it helps:** cheap retrieval practice exactly at node granularity; doubles as
the retrieval proof the mastery gate wants before promoting to `mastered`.

## 10. Cross-vault prerequisite bridges

**What:** let a physics vault declare maths nodes as external prerequisites
(vectors → mechanics, calculus → kinematics) without merging vaults: an
`external_prerequisites: [{vault: maths, id: 594}]` field the flow zone reads
across vault boundaries.

**Why it helps:** for multi-subject learners the real graph *is* cross-subject;
physics flow zone should gate on your actual calculus mastery, not a copy of it.

**Caveat:** keep it read-only across vaults (no cross-vault writes) — same
single-source-of-truth rule as Anki.

## 11. Voice/mobile error capture

**What:** `log_error` from a phone: dictate the mistake, a share-sheet/shortcut
appends it to an inbox note that syncs into the vault; triage picks it up with the
`#unanalyzed` queue.

**Why it helps:** most real mistakes happen away from the terminal (textbook work,
past papers on paper). Capture friction is the difference between a logged error
and a forgotten one — the 5-second rule is the whole design.

---

## Non-goals (considered and rejected)

- **Two-way Anki/external-SRS sync** — see entry 1; dual schedulers drift.
- **A web/GUI app** — the terminal + Obsidian split is deliberate: Obsidian owns
  reading/ticking, scripts own state transitions. A GUI adds a third writer.
- **Replacing FSRS with a custom scheduler** — FSRS is the best-validated open
  scheduler; the leverage is in the graph layer above it, not below.
