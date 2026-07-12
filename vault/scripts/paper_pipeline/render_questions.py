#!/usr/bin/env python3
"""render_questions.py — full-question PNG renders for question-bank entries.

For every entry in papers/question_bank.json, crops the complete question
region out of the original QP PDF (figures included, pixel-perfect — no
vision model needed) so practice notes and booklets can embed it.

Usage (from vault root):
  python scripts/paper_pipeline/render_questions.py           # render missing
  python scripts/paper_pipeline/render_questions.py --force   # re-render all

Outputs:
  papers/renders/{paper_id}_q{n}_p{i}.png   (i = 1..k segments, top to bottom)

Idempotent: a question whose _p*.png files already exist is skipped unless
--force. Only questions present in the bank are rendered.
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None  # pip install pymupdf (only needed when actually processing PDFs)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract import split_questions  # reuse the QP boundary logic

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-render even if PNGs exist")
    args = ap.parse_args()

    if not BANK.exists():
        sys.exit("No question bank found - run merge_bank.py first.")
    RENDERS.mkdir(parents=True, exist_ok=True)

    by_paper = wanted_by_paper(load_bank())
    rendered = skipped = 0
    for paper_id in sorted(by_paper):
        r, s = render_paper(paper_id, by_paper[paper_id], args.force)
        rendered += r
        skipped += s
    print(f"Rendered {rendered} questions ({skipped} already present) -> {RENDERS}")


if __name__ == "__main__":
    main()
