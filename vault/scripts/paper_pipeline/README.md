# Paper pipeline

Turns a folder of past-paper PDFs (that you have the right to use) into a
topic-tagged question bank + per-node practice notes/booklets.
Full guide: `../../../docs/05-paper-pipeline.md`.

Requires: `pip install pymupdf`.

```bash
python extract.py --src "path/to/your/papers" --years 2017-2025   # split QPs/MS
python extract.py --batches                                       # bundle for LLM
python process_batches.py --limit 5                               # pilot wave
python process_batches.py --workers 4                             # the rest
python merge_bank.py                                              # -> papers/question_bank.json
python render_questions.py                                        # PNG crops
python gen_practice.py                                            # notes + booklets + links
```

## Plugging in your LLM

`process_batches.py` shells out to an agent CLI per batch. The shipped `--engine`
options reflect the reference setup (`hermes`, `opencode`); to use anything else,
edit `run_batch()` — any CLI that accepts a prompt string and can read/write files
works (`claude -p "<prompt>"`, a local-model wrapper, etc.). The contract per batch:
read `system_prompt.txt` + `{batch_id}.json`, write `results/{batch_id}_result.json`
as a JSON array of bank entries. The driver validates (≥60% of expected question ids),
retries once, and circuit-breaks after 3 straight failures.

## Layout notes

The QP splitter and mark-scheme table parser are written for CIE-style PDFs
(2017+ table-format mark schemes). Other boards: adapt `split_questions()` /
`split_markscheme()` and verify crops on 2–3 papers before scaling.

`papers/question_bank.json`, `papers/extracted/`, `papers/renders|booklets|figures/`
are **gitignored** — extracted exam content is copyrighted and stays local.
