#!/usr/bin/env python3
"""render_questions.py — full-question PNG renders for question-bank entries.

For every entry in papers/question_bank.json, crops the complete question
region out of the original QP PDF (figures included, pixel-perfect — no
vision model needed) so practice notes and booklets can embed it. A second
pass crops each question's MARK SCHEME table rows out of the original MS PDF
(authoritative formatting — replaces lossy extracted text in notes/booklets).

Usage (from vault root):
  python scripts/paper_pipeline/render_questions.py           # render missing
  python scripts/paper_pipeline/render_questions.py --force   # re-render all
  python scripts/paper_pipeline/render_questions.py --ms-only # only MS crops

Outputs:
  papers/renders/{paper_id}_q{n}_p{i}.png      question (i = 1..k segments)
  papers/renders/{paper_id}_ms_q{n}_p{i}.png   mark-scheme rows for question n

Idempotent: a question whose _p*.png files already exist is skipped unless
--force. Only questions present in the bank are rendered.
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract import split_questions, MS_QNUM_RE  # reuse QP boundaries + MS row logic

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

VAULT = Path(__file__).resolve().parents[2]
BANK = VAULT / "papers" / "question_bank.json"
EXTRACTED = VAULT / "papers" / "extracted"
RENDERS = VAULT / "papers" / "renders"

ID_RE = re.compile(r"^(.*)_q(\d+)$")


def load_bank() -> list[dict]:
    data = json.loads(BANK.read_text(encoding="utf-8"))
    return data["questions"] if isinstance(data, dict) else data


def wanted_by_paper(entries) -> dict[str, set[int]]:
    """paper_id -> {qnums needed}."""
    by_paper: dict[str, set[int]] = {}
    for e in entries:
        m = ID_RE.match(e["id"])
        if not m:
            print(f"WARN: unparseable entry id {e['id']!r}, skipped")
            continue
        by_paper.setdefault(m.group(1), set()).add(int(m.group(2)))
    return by_paper


def existing(paper_id: str, qnum: int) -> list[Path]:
    return sorted(RENDERS.glob(f"{paper_id}_q{qnum}_p*.png"),
                  key=lambda p: int(p.stem.rsplit("_p", 1)[1]))


def render_paper(paper_id: str, qnums: set[int], force: bool) -> tuple[int, int]:
    """Render the wanted questions of one paper. Returns (rendered, skipped)."""
    meta_file = EXTRACTED / f"{paper_id}.json"
    if not meta_file.exists():
        print(f"WARN: {paper_id}: no extracted JSON, skipped")
        return 0, 0
    todo = qnums if force else {q for q in qnums if not existing(paper_id, q)}
    if not todo:
        return 0, len(qnums)
    src = Path(json.loads(meta_file.read_text(encoding="utf-8"))["source_pdf"])
    if not src.exists():
        print(f"WARN: {paper_id}: source PDF missing ({src}), skipped")
        return 0, 0
    doc = fitz.open(src)
    segs_by_qnum = {q["qnum"]: q["segments"] for q in split_questions(doc)}
    done = 0
    for qn in sorted(todo):
        segs = segs_by_qnum.get(qn)
        if not segs:
            print(f"WARN: {paper_id} q{qn}: boundary not found on re-split")
            continue
        for old in existing(paper_id, qn):  # clear stale segment files on --force
            old.unlink()
        for i, (p, top, bot) in enumerate(segs, 1):
            rect = fitz.Rect(20, top, doc[p].rect.width - 20, bot)
            pix = doc[p].get_pixmap(clip=rect, matrix=fitz.Matrix(2, 2))
            pix.save(RENDERS / f"{paper_id}_q{qn}_p{i}.png")
        done += 1
    doc.close()
    return done, len(qnums) - len(todo)


def existing_ms(paper_id: str, qnum: int) -> list[Path]:
    return sorted(RENDERS.glob(f"{paper_id}_ms_q{qnum}_p*.png"),
                  key=lambda p: int(p.stem.rsplit("_p", 1)[1]))


def ms_regions(doc: fitz.Document) -> dict[int, list[tuple[int, fitz.Rect]]]:
    """qnum -> [(page_index, rect)] unions of the MS table rows for that question.

    Mirrors extract.split_markscheme()'s row classification, but keeps row
    bboxes instead of text. Rows are only assigned after the first real
    'Question | Answer' header row — this skips the general marking-principles
    tables at the front, whose rows also start with bare digits."""
    regions: dict[int, list[tuple[int, fitz.Rect]]] = {}
    current = None
    seen_header = False   # first 'Question|Answer' header marks the end of the
    # marking-principles front matter (whose rows also start with bare digits)
    for pi in range(doc.page_count):
        try:
            tables = doc[pi].find_tables().tables
        except Exception:
            continue
        for t in tables:
            rows_text = t.extract()
            qband = t.bbox[0] + 0.15 * (t.bbox[2] - t.bbox[0])
            for ri, row in enumerate(t.rows):
                raw = [str(c or "").replace("\n", " ").strip() for c in rows_text[ri]]
                if "Question" in raw:
                    seen_header = True
                    continue
                if not seen_header:
                    continue
                if not any(raw):
                    continue   # empty separator row: never union (bleeds into
                    # the previous question when it precedes the next header)
                # a question number must sit in the LEFTMOST column band —
                # header/data column indices are misaligned (merged cells), and
                # a bare Marks value ('3') as the first non-empty cell would
                # otherwise hijack the current-question tracker
                for ci, txt in enumerate(raw):
                    if not txt:
                        continue
                    cell_rect = row.cells[ci] if ci < len(row.cells) else None
                    if cell_rect and cell_rect[0] <= qband:
                        m = MS_QNUM_RE.match(txt)
                        if m and 1 <= int(m.group(1)) <= 20:
                            current = int(m.group(1))
                    break  # only the first non-empty cell can be the qnum
                if current is None:
                    continue
                r = fitz.Rect(row.bbox)
                if r.height < 2:          # separator artifacts
                    continue
                lst = regions.setdefault(current, [])
                if lst and lst[-1][0] == pi:
                    lst[-1] = (pi, lst[-1][1] | r)   # one union rect per page
                else:
                    lst.append((pi, r))
    return regions


def render_ms(paper_id: str, qnums: set[int], force: bool) -> tuple[int, int]:
    """Render mark-scheme crops for the wanted questions. Returns (rendered, skipped)."""
    meta_file = EXTRACTED / f"{paper_id}.json"
    if not meta_file.exists():
        return 0, 0
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    ms = meta.get("ms_pdf")
    if not ms or not Path(ms).exists():
        return 0, 0
    todo = qnums if force else {q for q in qnums if not existing_ms(paper_id, q)}
    if not todo:
        return 0, len(qnums)
    doc = fitz.open(ms)
    regions = ms_regions(doc)
    done = 0
    for qn in sorted(todo):
        regs = regions.get(qn)
        if not regs:
            print(f"WARN: {paper_id} q{qn}: no MS table rows found")
            continue
        for old in existing_ms(paper_id, qn):
            old.unlink()
        for i, (pi, rect) in enumerate(regs, 1):
            pad = fitz.Rect(rect.x0 - 4, rect.y0 - 4, rect.x1 + 4, rect.y1 + 4)
            pad = pad & doc[pi].rect
            pix = doc[pi].get_pixmap(clip=pad, matrix=fitz.Matrix(2, 2))
            pix.save(RENDERS / f"{paper_id}_ms_q{qn}_p{i}.png")
        done += 1
    doc.close()
    return done, len(qnums) - len(todo)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-render even if PNGs exist")
    ap.add_argument("--ms-only", action="store_true", help="skip question renders, only MS crops")
    args = ap.parse_args()

    if not BANK.exists():
        sys.exit("No question bank found - run merge_bank.py first.")
    RENDERS.mkdir(parents=True, exist_ok=True)

    by_paper = wanted_by_paper(load_bank())
    rendered = skipped = 0
    if not args.ms_only:
        for paper_id in sorted(by_paper):
            r, s = render_paper(paper_id, by_paper[paper_id], args.force)
            rendered += r
            skipped += s
        print(f"Rendered {rendered} questions ({skipped} already present) -> {RENDERS}")
    ms_rendered = ms_skipped = 0
    for paper_id in sorted(by_paper):
        r, s = render_ms(paper_id, by_paper[paper_id], args.force)
        ms_rendered += r
        ms_skipped += s
    print(f"Rendered {ms_rendered} MS crops ({ms_skipped} already present) -> {RENDERS}")


if __name__ == "__main__":
    main()
