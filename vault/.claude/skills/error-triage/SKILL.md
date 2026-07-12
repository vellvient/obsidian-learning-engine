---
name: error-triage
description: Batch-analyse #unanalyzed entries in "00 - Error Log.md" — classify each error, find the root cause and prerequisite gap using the vault's knowledge graph, prescribe fixes, and update the weak-spot trackers. Use at the end of a study session, or whenever the user says "triage my errors", "analyse my mistakes", or "what are my gaps".
---

# Error Triage — batch analysis of logged math errors

Errors are captured instantly during study with `python log_error.py <id|context> "<what happened>"` (optionally `--shot` for a screenshot, `--again` to FSRS-punish the subskill). This skill is the deferred deep-analysis pass, run in batch so analysis never interrupts a study session.

## Procedure

1. **Collect.** Read `00 - Error Log.md`. Every `###` entry containing `#unanalyzed` is pending. If there are none, say so and stop. If an entry embeds a screenshot (`![[attachments/errors/...]]`), Read the image file — it usually contains the actual problem and the user's wrong working.

2. **Analyse each entry.** For each pending error, fill in the four `_pending triage_` fields:
   - **Error type** — one of:
     - `Slip` — knew it, careless execution (sign error, arithmetic, copying)
     - `Procedural bug` — systematically wrong step in a known method
     - `Concept gap` — the underlying idea is missing or wrong
     - `Prerequisite gap` — the failure is actually in an *earlier* skill
     - `Strategy blank` — couldn't choose an approach (common on UKMT/competition problems)
     - `Misread` — misinterpreted the question
   - **Root cause** — one or two sentences, specific to the working, not generic.
   - **Fix / rule to remember** — a short imperative rule the user can rehearse (e.g. "dividing an inequality by a negative flips the sign — check direction as the last step").
   - **Prerequisite gap** — if the root cause lives upstream, name the exact exercise note. Open the exercise note (e.g. `339 - Solving linear inequalities in one variable.md`), read its `prerequisites:` frontmatter, and check the mastery of those prereq notes. Link the culprit as `[[num - name]]`; write `None` if the error is self-contained.

   Remove the `#unanalyzed` tag from the heading once the entry is filled in (leave the heading otherwise unchanged).

3. **Detect patterns.** Compare the new entries against ALL previous entries in the log. Same error type on the same topic 2+ times, or the same rule violated in different topics, is a pattern — call it out explicitly.

4. **Update the summary table.** Rebuild the `## Error Type Summary` table near the top of the log: one row per distinct error type, with count and last-seen date.

5. **Propagate to the study system.**
   - If a prerequisite gap or repeated pattern names an exercise, add/update it in `00 - Weak Spots Priority.md` with a one-line reason (morning.py parses `[[num - ...]]` links from that note to boost priorities).
   - For entries whose subskill was NOT already graded with `--again`, offer the grade command: `python srs_fsrs.py --grade "<file>.md:<subskill>: <name>" Again`. Ask before running these — the user may have logged a slip they don't want to punish.

6. **Report.** End with a compact summary: N errors triaged, the type breakdown, any patterns found, and the single highest-leverage fix (the one gap that, if closed, prevents the most future errors — prefer gaps that are prerequisites of many not-yet-mastered skills in the graph).

## Judgment guidance

- Severity self-ratings (`--sev`) are the user's in-the-moment guess; you may overrule them with evidence and say why.
- Prefer diagnosing ONE deep cause over listing five shallow ones. Math Academy's model: an error on skill X is most often a fluency failure on a prerequisite of X, not on X itself.
- "Strategy blank" on competition problems (UKMT etc.) is usually not a vault-graph gap — recommend a worked-example study or a tactic (smaller cases, draw it, parity, invariants) instead of prerequisite drilling.
- Do not invent entries, delete history, or touch entries already analysed (no `#unanalyzed` tag).
