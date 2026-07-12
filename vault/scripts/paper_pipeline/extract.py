#!/usr/bin/env python3
"""
extract.py — CIE past-paper -> per-question JSON (free, local, no LLM).

Walks a downloaded past-paper tree (e.g. path/to/your/papers), finds
QP/MS pairs by CIE filename convention ({code}_{s|w|m}{yy}_qp_{comp}.pdf),
splits each question paper into individual questions with PyMuPDF, pairs each
question with its mark-scheme text, flags questions that contain figures and
exports cropped PNGs of those for the (free) Gemini vision pass.

Usage (from vault root):
  python scripts/paper_pipeline/extract.py --src "path/to/your/papers" --years 2017-2025
  python scripts/paper_pipeline/extract.py --src ... --years 2020-2025 --codes 9709 --limit 6
  python scripts/paper_pipeline/extract.py --batches          # bundle extracted JSON for Hermes

Outputs:
  papers/extracted/{paper_id}.json      one file per QP (paper_id e.g. 9709_m23_qp_12)
  papers/figures/{paper_id}_q{n}_p{p}.png   crops for needs_vision questions
  .engine/paper_mining/batch_*.json     with --batches (5 papers per batch)
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

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

VAULT = Path(__file__).resolve().parents[2]
OUT_EXTRACTED = VAULT / "papers" / "extracted"
OUT_FIGURES = VAULT / "papers" / "figures"
BATCH_DIR = VAULT / ".engine" / "paper_mining"

FNAME_RE = re.compile(r"^(\d{4})_([smw])(\d{2})_qp_(\d+)\.pdf$", re.I)
QSTART_X_MAX = 62          # question numbers sit at left margin x0 ~49
QSTART_RE = re.compile(r"^(\d{1,2})(?:[\s.].*)?$")
NOISE_RE = re.compile(r"^\.{6,}\s*(\[\d+\])?$")  # dotted answer lines
SKIP_LINE_RE = re.compile(
    r"(©\s*UCLES|\[Turn over|BLANK PAGE|Additional page|"
    r"If you need additional answer space|continuation of|"
    r"If you use the following lined page|question number\(s\)|must be clearly shown|"
    r"^\*\d{10,}\*$|Permission to reproduce|Cambridge Assessment|"
    r"^\d{4}/\d{2}(/[A-Z]+)*/?[A-Z]*/\d{2}$)", re.I)
PUA_RE = re.compile(r"[-]")  # Symbol-font private-use glyphs in MS tables
SESSION_NAME = {"s": "May/June", "w": "Oct/Nov", "m": "Feb/March"}


def find_pairs(src: Path, codes, y0, y1):
    """Yield (qp_path, ms_path_or_None, meta) for matching papers."""
    for qp in sorted(src.rglob("*.pdf")):
        m = FNAME_RE.match(qp.name)
        if not m:
            continue
        code, sess, yy, comp = m.group(1), m.group(2).lower(), m.group(3), m.group(4)
        year = 2000 + int(yy)
        if codes and code not in codes:
            continue
        if not (y0 <= year <= y1):
            continue
        ms = qp.with_name(f"{code}_{sess}{yy}_ms_{comp}.pdf")
        yield qp, (ms if ms.exists() else None), {
            "code": code, "session": SESSION_NAME[sess], "year": year,
            "component": comp, "paper_id": f"{code}_{sess}{yy}_qp_{comp}",
        }


def clean_lines(text: str) -> str:
    out = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s or NOISE_RE.match(s) or SKIP_LINE_RE.search(s):
            continue
        out.append(s)
    return "\n".join(out)


BACKMATTER_RE = re.compile(
    r"(Local Examinations Syndicate|cambridgeinternational\.org after the live|BLANK PAGE)", re.I)


def last_content_page(doc: fitz.Document) -> int:
    for pi in range(doc.page_count - 1, 0, -1):
        text = doc[pi].get_text().strip()
        if len(text) > 40 and not BACKMATTER_RE.search(text):
            return pi
    return doc.page_count - 1


def split_questions(doc: fitz.Document):
    """Return [{qnum, segments:[(page_idx, y_top, y_bottom)], text}] for a QP."""
    starts = []  # (page_idx, y0, qnum)
    for pi in range(1, doc.page_count):  # page 0 = cover
        for b in doc[pi].get_text("blocks"):
            x0, y0, x1, y1, text = b[0], b[1], b[2], b[3], b[4]
            first = text.strip().splitlines()[0].strip() if text.strip() else ""
            m = QSTART_RE.match(first)
            if m and x0 < QSTART_X_MAX:
                starts.append((pi, y0, int(m.group(1))))
    # keep only monotonically increasing question numbers (guards against
    # stray numeric blocks like equation numbers)
    filtered, last = [], 0
    for pi, y0, qn in starts:
        if qn == last + 1:
            filtered.append((pi, y0, qn))
            last = qn
    questions = []
    for i, (pi, y0, qn) in enumerate(filtered):
        if i + 1 < len(filtered):
            npi, ny0, _ = filtered[i + 1]
        else:
            npi = last_content_page(doc)
            ny0 = doc[npi].rect.height
        segments = []
        for p in range(pi, npi + 1):
            top = y0 - 4 if p == pi else 50           # 50 = skip running header
            bot = ny0 - 4 if p == npi else doc[p].rect.height - 55  # skip footer
            if bot - top > 25:
                segments.append((p, top, bot))
        text_parts = []
        for p, top, bot in segments:
            rect = fitz.Rect(30, top, doc[p].rect.width - 30, bot)
            text_parts.append(doc[p].get_text(clip=rect))
        questions.append({"qnum": qn, "segments": segments,
                          "text": clean_lines("\n".join(text_parts))})
    return questions


def detect_figures(doc: fitz.Document, q: dict) -> bool:
    """True if the question's area contains raster images or substantial vector art."""
    for p, top, bot in q["segments"]:
        page = doc[p]
        rect = fitz.Rect(30, top, page.rect.width - 30, bot)
        if page.get_image_info():
            for info in page.get_image_info():
                if fitz.Rect(info["bbox"]).intersects(rect):
                    return True
        big = 0
        for d in page.get_drawings():
            r = d["rect"]
            if r.intersects(rect) and r.width > 25 and r.height > 25:
                big += 1
                if big >= 5:
                    return True
    return False


def export_crops(doc: fitz.Document, q: dict, paper_id: str) -> list:
    OUT_FIGURES.mkdir(parents=True, exist_ok=True)
    files = []
    for p, top, bot in q["segments"]:
        rect = fitz.Rect(20, top, doc[p].rect.width - 20, bot)
        pix = doc[p].get_pixmap(clip=rect, matrix=fitz.Matrix(2, 2))
        name = f"{paper_id}_q{q['qnum']}_p{p + 1}.png"
        pix.save(OUT_FIGURES / name)
        files.append(name)
    return files


MS_QNUM_RE = re.compile(r"^(\d{1,2})(\([a-z]\))?(\([ivx]+\))?$")


def split_markscheme(ms_path: Path):
    """Map top-level question number -> mark scheme text via table extraction.

    Modern CIE mark schemes (2017+) lay out marking as tables:
    Question | Answer | Marks | Guidance. PyMuPDF's find_tables recovers the
    rows far more cleanly than raw text extraction (which scrambles math)."""
    doc = fitz.open(ms_path)
    chunks, current = {}, None
    for pi in range(doc.page_count):
        try:
            tables = doc[pi].find_tables().tables
        except Exception:
            continue
        for t in tables:
            for row in t.extract():
                cells = [PUA_RE.sub("", str(c)).replace("\n", " ").strip()
                         for c in row if c and str(c).strip()]
                if not cells or cells[0] in ("Question",) or "Answer" in cells[:2]:
                    continue
                m = MS_QNUM_RE.match(cells[0])
                if m and 1 <= int(m.group(1)) <= 20:
                    current = int(m.group(1))
                    chunks.setdefault(current, [])
                    part = m.group(2) or ""
                    body = " | ".join(cells[1:])
                    if body:
                        chunks[current].append((part + " " + body).strip())
                elif current is not None and cells:
                    chunks[current].append(" | ".join(cells))
    doc.close()
    return {k: "\n".join(v) for k, v in chunks.items()}


def extract_paper(qp_path: Path, ms_path, meta: dict) -> dict:
    doc = fitz.open(qp_path)
    questions = split_questions(doc)
    ms_chunks = split_markscheme(ms_path) if ms_path else {}
    for q in questions:
        q["needs_vision"] = detect_figures(doc, q)
        q["figure_pngs"] = export_crops(doc, q, meta["paper_id"]) if q["needs_vision"] else []
        q["figure_description"] = None  # filled by vision_pass.py
        q["ms_text"] = ms_chunks.get(q["qnum"], "")
        q.pop("segments")
    doc.close()
    return {**meta, "source_pdf": str(qp_path), "ms_pdf": str(ms_path) if ms_path else None,
            "n_questions": len(questions), "questions": questions}


MIN_TAG_ID = 250  # exclude primary/KS3 skills from the tagging index


def load_topic_index() -> str:
    """A-Level-relevant subset of the master index for topic tagging."""
    src = VAULT / ".engine" / "prereq_mining" / "master_index_compact.txt"
    lines = []
    for ln in src.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"^(\d+)\|", ln)
        if m and int(m.group(1)) >= MIN_TAG_ID:
            lines.append(ln)
    return "\n".join(lines)


def make_batches(papers_per_batch: int = 5):
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(OUT_EXTRACTED.glob("*.json"))
    if not files:
        print("No extracted papers found - run extraction first.")
        return
    topic_index = load_topic_index()
    manifest = []
    for bi in range(0, len(files), papers_per_batch):
        group = files[bi:bi + papers_per_batch]
        batch_id = f"batch_{bi // papers_per_batch + 1:03d}"
        papers = []
        for f in group:
            try:
                papers.append(json.loads(f.read_text(encoding="utf-8")))
            except Exception as e:
                print(f"WARN: skipping {f.name} (unreadable: {e})")
        payload = {"batch_id": batch_id, "topic_index": topic_index,
                   "papers": papers}
        # figures are described as text already; strip png filenames from payload
        for p in payload["papers"]:
            for q in p["questions"]:
                q.pop("figure_pngs", None)
        (BATCH_DIR / f"{batch_id}.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        manifest.append({"batch_id": batch_id, "papers": [f.stem for f in group],
                         "status": "pending"})
    (BATCH_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (BATCH_DIR / "results").mkdir(exist_ok=True)
    print(f"Wrote {len(manifest)} batches ({papers_per_batch} papers each) to {BATCH_DIR}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", help="root of downloaded papers")
    ap.add_argument("--years", default="2017-2025", help="e.g. 2017-2025")
    ap.add_argument("--codes", default="", help="comma list, e.g. 9709,9231 (default: all)")
    ap.add_argument("--limit", type=int, default=0, help="stop after N papers (for testing)")
    ap.add_argument("--batches", action="store_true", help="bundle extracted JSON into Hermes batches")
    ap.add_argument("--papers-per-batch", type=int, default=5)
    args = ap.parse_args()

    if args.batches:
        make_batches(args.papers_per_batch)
        return
    if not args.src:
        ap.error("--src required (or use --batches)")

    y0, y1 = (int(x) for x in args.years.split("-"))
    codes = set(args.codes.split(",")) if args.codes else None
    OUT_EXTRACTED.mkdir(parents=True, exist_ok=True)

    n, vis_total = 0, 0
    for qp, ms, meta in find_pairs(Path(args.src), codes, y0, y1):
        try:
            data = extract_paper(qp, ms, meta)
        except Exception as e:
            print(f"FAIL {qp.name}: {e}")
            continue
        out = OUT_EXTRACTED / f"{meta['paper_id']}.json"
        out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        nv = sum(1 for q in data["questions"] if q["needs_vision"])
        vis_total += nv
        ms_hit = sum(1 for q in data["questions"] if q["ms_text"])
        print(f"{meta['paper_id']}: {data['n_questions']} questions, "
              f"{ms_hit} with MS text, {nv} need vision"
              + ("" if ms else "  [NO MARK SCHEME FOUND]"))
        n += 1
        if args.limit and n >= args.limit:
            break
    print(f"\nDone: {n} papers -> {OUT_EXTRACTED}  ({vis_total} questions flagged for vision pass)")


if __name__ == "__main__":
    main()
