# 05 — Past-Paper Pipeline (topical question banks)

Turn a folder of past-paper PDFs into a **topical practice system**: every graph node
links to practice material containing all past-paper questions tagged to it, sorted
easy→hard, with folded answers and a printable booklet.

**Bring your own PDFs.** This repo ships code only — no exam content. Use papers you
have the right to use; generated banks/renders/booklets are gitignored by default so
they stay local.

Requires: `pip install pymupdf`, plus any LLM CLI for the tagging step.

## The design (and a lesson about vision models)

The pipeline was originally designed with a vision-model pass to describe figures for
the tagging model. **That pass was retired**, for a reason worth keeping:

- *Serving* needs no AI — each question is rendered as a **PNG crop of the original
  PDF**, so figures arrive pixel-perfect for free.
- *Tagging* works from text alone — the pilot batch hit 98% topic coverage with zero
  figure descriptions.

Cheapest correct architecture: local PDF extraction (free) → cheap-LLM text tagging →
local rendering (free). A strong model is only used to spot-check samples.

## The six steps

```bash
# 1. Extract: walk the PDF tree, split question papers into per-question text,
#    pair each with its mark scheme (idempotent)
python scripts/paper_pipeline/extract.py --src "path/to/your/papers" --years 2017-2025

# 2. Bundle into batches for the tagging model (embeds your vault's topic index)
python scripts/paper_pipeline/extract.py --batches

# 3. Drive an LLM over the batches (validates results, retries, merges every 5)
python scripts/paper_pipeline/process_batches.py --limit 10   # first wave
python scripts/paper_pipeline/process_batches.py --workers 4  # the rest, parallel

# 4. Merge + validate the bank (standalone re-run any time)
python scripts/paper_pipeline/merge_bank.py     # -> papers/question_bank.json

# 5. Render full-question PNG crops from the source PDFs (idempotent)
python scripts/paper_pipeline/render_questions.py

# 6. Generate per-node practice notes + booklets + note links (idempotent)
python scripts/paper_pipeline/gen_practice.py
```

## Bank entry schema

```json
{
  "id": "9709_s23_qp_12_q4", "code": "9709", "year": 2023, "session": "s",
  "component": "12", "qnum": 4, "marks": 5,
  "question": "full question text...",
  "final_answers": ["x = 3, x = -2"],
  "markscheme_points": ["M1 attempt to factorise", "A1 both roots"],
  "topic_node_ids": [11, 12],
  "difficulty": "medium", "has_figure": false
}
```

`topic_node_ids` are **your vault's exercise numbers** — that's what makes the bank
topical: questions can be served per graph node, filtered by flow zone or FSRS-due.

## What gets generated per node

- **`practice/{num} - Practice.md`** — auto-generated (never hand-edit): questions as
  embedded PNG renders sorted easy→hard, each with a folded `> [!success]-` answer
  callout (final answers + mark-scheme points + a link to the original MS PDF for
  when extracted text isn't enough).
- **`papers/booklets/{num} - Booklet.pdf`** — printable: one question per page,
  answers section at the back.
- An idempotent `<!-- auto:practice-link -->` block inserted into the node's note.
- `study_today.py` marks picks that have practice material with `p` and lists them.

The practice loop: attempt → self-mark against the folded answer → miss ⇒
`log_error.py <node> "..." --again` → grade FSRS.

## Driving the tagging model

`process_batches.py` invokes an agent CLI per batch with a fixed prompt (read the
system prompt + batch JSON, write a result JSON array). It validates each result
(≥60% of expected question ids present), retries once, tracks state in a manifest
(safe to kill and re-run — completed batches are never re-sent), and circuit-breaks
after 3 consecutive failures (rate limits happen; just re-run later).

Adapting to your model: the `run_batch()` function builds the CLI command — swap in
any CLI that accepts a prompt and can read/write files (`claude -p`, a local model
wrapper, etc.). Cheap models are genuinely sufficient here: the reference build
tagged ~2,000+ questions at ~98% topic coverage with a budget model, QA-sampled by a
strong model at ~0 error rate on tags.

Known quality notes from the reference run (acceptable, don't over-engineer):
- "Show that..." questions get marking descriptions instead of clean final answers
  (~15–25% flagged UNCLEAR) — the mark-scheme points + linked MS PDF cover it.
- Mark schemes with unusual glyph encodings can mojibake Greek letters in extracted
  text — again, the MS PDF link is the fallback.

## Adapting extraction to your exam board

`extract.py`'s question-splitting logic is written for CIE-style layouts (question
numbers at line starts, mark schemes as tables). For other boards:
- The QP splitter (`split_questions`) keys on question-number patterns — adjust the
  regex for your board's layout.
- The MS parser uses PyMuPDF `find_tables()` — works for table-format mark schemes
  (CIE 2017+). Older/prose-style mark schemes need a different parser, or skip MS
  text extraction and rely on the PDF link.
- Verify on 2–3 papers (render the crops, eyeball boundaries) before running the corpus.
