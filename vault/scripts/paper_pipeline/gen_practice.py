#!/usr/bin/env python3
"""gen_practice.py — topical paper system: per-node practice notes + PDF booklets.

Reads papers/question_bank.json and, for every graph node with tagged
questions, generates:

  practice/{num} - Practice.md        AUTO-GENERATED note (never hand-edit):
                                      questions easy->hard as embedded renders,
                                      answers folded below each, MS PDF links
  papers/booklets/{num} - Booklet.pdf printable fallback: one question per
                                      page, answers section at the back
  exercise note                       idempotent marker-based Practice link

Usage (from vault root):
  python scripts/paper_pipeline/gen_practice.py                # all nodes in bank
  python scripts/paper_pipeline/gen_practice.py --nodes 581,674
  python scripts/paper_pipeline/gen_practice.py --no-booklets  # notes/links only

Run render_questions.py first (embeds papers/renders/*.png).
Re-run after every merge_bank.py — practice notes are fully rewritten.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import re
import sys
import textwrap
from pathlib import Path

import fitz  # PyMuPDF

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

VAULT = Path(__file__).resolve().parents[2]
BANK = VAULT / "papers" / "question_bank.json"
EXTRACTED = VAULT / "papers" / "extracted"
RENDERS = VAULT / "papers" / "renders"
PRACTICE = VAULT / "practice"
BOOKLETS = VAULT / "papers" / "booklets"

ID_RE = re.compile(r"^(.*)_q(\d+)$")
DIFF_RANK = {"easy": 0, "medium": 1, "hard": 2}
MARK_START = "<!-- auto:practice-link -->"
MARK_END = "<!-- /auto:practice-link -->"

# latin-1-safe text for PDF booklets (helv base font); the practice note keeps
# the original unicode — this is only for the printable fallback
PDF_CHAR_MAP = str.maketrans({
    "−": "-", "×": "x", "÷": "/", "√": "sqrt",
    "π": "pi", "α": "alpha", "β": "beta", "θ": "theta",
    "λ": "lambda", "μ": "mu", "ω": "omega", "Σ": "Sigma",
    "∑": "Sigma", "∫": "integral", "≤": "<=", "≥": ">=",
    "≠": "!=", "≈": "~=", "²": "^2", "³": "^3",
    "’": "'", "‘": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "→": "->", "°": " deg",
})


def pdf_safe(s: str) -> str:
    return s.translate(PDF_CHAR_MAP).encode("latin-1", "replace").decode("latin-1")


def load_bank() -> list[dict]:
    data = json.loads(BANK.read_text(encoding="utf-8"))
    return data["questions"] if isinstance(data, dict) else data


def note_for(num: int) -> Path | None:
    hits = [p for p in VAULT.glob(f"{num} - *.md") if p.is_file()]
    return hits[0] if hits else None


_ms_pdf_cache: dict[str, str | None] = {}


def ms_pdf_uri(paper_id: str) -> str | None:
    if paper_id not in _ms_pdf_cache:
        f = EXTRACTED / f"{paper_id}.json"
        ms = json.loads(f.read_text(encoding="utf-8")).get("ms_pdf") if f.exists() else None
        _ms_pdf_cache[paper_id] = Path(ms).as_uri() if ms and Path(ms).exists() else None
    return _ms_pdf_cache[paper_id]


def renders_of(entry_id: str) -> list[Path]:
    m = ID_RE.match(entry_id)
    if not m:
        return []
    return sorted(RENDERS.glob(f"{m.group(1)}_q{m.group(2)}_p*.png"),
                  key=lambda p: int(p.stem.rsplit("_p", 1)[1]))


def ms_renders_of(entry_id: str) -> list[Path]:
    m = ID_RE.match(entry_id)
    if not m:
        return []
    return sorted(RENDERS.glob(f"{m.group(1)}_ms_q{m.group(2)}_p*.png"),
                  key=lambda p: int(p.stem.rsplit("_p", 1)[1]))


_tex_cache: dict[str, list[str]] | None = None


def tex_finals(entry_id: str) -> list[str] | None:
    """LaTeX-converted final_answers from papers/answers_tex.json (if present)."""
    global _tex_cache
    if _tex_cache is None:
        f = VAULT / "papers" / "answers_tex.json"
        _tex_cache = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    return _tex_cache.get(entry_id)


def sort_key(e: dict):
    return (DIFF_RANK.get(e.get("difficulty"), 1), e.get("marks") or 0)


# ---------------------------------------------------------------- practice note

def build_note(num: int, name: str, entries: list[dict]) -> str:
    today = dt.date.today().isoformat()
    lines = [
        "---",
        "tags: [practice]",
        "auto: true",
        f"node: {num}",
        f"generated: {today}",
        "---",
        "",
        f"# {num} — Practice: {name}",
        "",
        f"**{len(entries)} tagged past-paper questions** (easy → hard) · "
        f"printable: [[papers/booklets/{num} - Booklet.pdf|booklet]]",
        "",
        f"Node: [[{num} - {name}]]" if name != f"node {num}" else "",
        "",
        "> [!tip]- Loop",
        "> Attempt on paper → unfold the answer and self-mark → on a miss run",
        f"> `python log_error.py {num}<subskill> \"what happened\" --again`",
        "> → grade the node's FSRS card as usual.",
        "",
        "> AUTO-GENERATED from papers/question_bank.json by gen_practice.py — do not hand-edit.",
        "",
    ]
    for i, e in enumerate(entries, 1):
        lines.append("---")
        lines.append("")
        lines.append(f"## Q{i} · {e['id']} · {e['marks']} marks · {e.get('difficulty', '?')}")
        pngs = renders_of(e["id"])
        if pngs:
            lines.extend(f"![[papers/renders/{p.name}]]" for p in pngs)
        else:  # render missing — fall back to extracted text
            lines.append("```")
            lines.append(e.get("question", "").strip())
            lines.append("```")
        lines.append("")
        lines.append("> [!success]- Answer & markscheme")
        finals = tex_finals(e["id"]) or [a for a in e.get("final_answers") or [] if a]
        finals = [a for a in finals if a]
        if finals:
            lines.append("> **Final:** " + " · ".join(finals))
        ms_pngs = ms_renders_of(e["id"])
        if ms_pngs:
            lines.extend(f"> ![[papers/renders/{p.name}]]" for p in ms_pngs)
        else:  # no MS crop (pre-2017 layout etc.) — fall back to extracted points
            for pt in e.get("markscheme_points") or []:
                lines.append(f"> - {pt}")
        uri = ms_pdf_uri(ID_RE.match(e["id"]).group(1))
        if uri:
            lines.append(f"> [Original MS PDF]({uri})")
        lines.append("")
    return "\n".join(ln for ln in lines if ln is not None) + "\n"


# ---------------------------------------------------------------- booklet PDF

def build_booklet(num: int, name: str, entries: list[dict], out: Path):
    """Question followed immediately by its mark-scheme crop — same page when it
    fits, overflow to the next page. No separate answers section."""
    a4 = fitz.paper_rect("a4")
    MARGIN, TOP, BOTTOM = 36, 45, 40
    doc = fitz.open()
    page = doc.new_page(width=a4.width, height=a4.height)
    page.insert_text((72, 120), pdf_safe(f"{num} - {name}"), fontsize=18)
    page.insert_text((72, 145), f"{len(entries)} past-paper questions, easy -> hard. "
                                f"Each question is followed by its markscheme.", fontsize=11)
    page.insert_text((72, 165), f"Generated {dt.date.today().isoformat()} by gen_practice.py",
                     fontsize=9, color=(0.5, 0.5, 0.5))
    y = a4.height  # force a new page for Q1

    def new_page(header: str | None = None):
        nonlocal page, y
        page = doc.new_page(width=a4.width, height=a4.height)
        y = TOP
        if header:
            page.insert_text((MARGIN, 30), pdf_safe(header), fontsize=9,
                             color=(0.35, 0.35, 0.35))

    def place_image(png: Path, header: str, max_h_frac: float = 1.0):
        """Place an image at the cursor, new page if it doesn't fit."""
        nonlocal y
        pix = fitz.Pixmap(str(png))
        scale = min((a4.width - 2 * MARGIN) / pix.width, 1.0)
        w, h = pix.width * scale, pix.height * scale
        max_h = (a4.height - TOP - BOTTOM) * max_h_frac
        if h > max_h:  # very tall crop: shrink to page height
            s2 = max_h / h
            w, h = w * s2, h * s2
        if y + h > a4.height - BOTTOM:
            new_page(header + "  (cont.)")
        page.insert_image(fitz.Rect(MARGIN, y, MARGIN + w, y + h), pixmap=pix)
        y += h + 8

    def emit_text(lines: list[tuple[str, float, float]], header: str):
        nonlocal y
        for line, size, indent in lines:
            if y > a4.height - BOTTOM:
                new_page(header + "  (cont.)")
            page.insert_text((MARGIN + 4 + indent, y), pdf_safe(line), fontsize=size)
            y += size * 1.45

    for i, e in enumerate(entries, 1):
        header = pdf_safe(f"Q{i}  |  {e['id']}  |  {e['marks']} marks  |  {e.get('difficulty', '?')}")
        new_page(header)  # every question starts on a fresh page
        for png in renders_of(e["id"]):
            place_image(png, header)
        # answer immediately below (same page when it fits)
        if y + 24 > a4.height - BOTTOM:
            new_page(header + "  (answer)")
        page.draw_line(fitz.Point(MARGIN, y + 2), fitz.Point(a4.width - MARGIN, y + 2),
                       color=(0.6, 0.6, 0.6), width=0.6)
        page.insert_text((MARGIN, y + 16), "Answer / markscheme", fontsize=10,
                         color=(0.2, 0.45, 0.2))
        y += 26
        ms_pngs = ms_renders_of(e["id"])
        if ms_pngs:
            for png in ms_pngs:
                place_image(png, header)
        else:  # no MS crop — text fallback for this question only
            lines: list[tuple[str, float, float]] = []
            finals = [a for a in e.get("final_answers") or [] if a]
            if finals:
                for ln in textwrap.wrap("Final: " + " ; ".join(finals), 100):
                    lines.append((ln, 9, 12))
            for pt in e.get("markscheme_points") or []:
                for j, ln in enumerate(textwrap.wrap(pt, 96)):
                    lines.append((("- " if j == 0 else "  ") + ln, 9, 18))
            emit_text(lines, header)
    doc.save(out, deflate=True)
    doc.close()


# ---------------------------------------------------------------- node link

def link_exercise_note(note: Path, num: int, n_questions: int):
    block = (f"{MARK_START}\n## 📄 Past-Paper Practice\n"
             f"[[{num} - Practice|{n_questions} tagged questions]] · "
             f"[[papers/booklets/{num} - Booklet.pdf|booklet]]\n{MARK_END}")
    text = note.read_text(encoding="utf-8")
    if MARK_START in text:
        new = re.sub(re.escape(MARK_START) + r".*?" + re.escape(MARK_END),
                     block, text, flags=re.S)
    else:
        new = text.rstrip("\n") + "\n\n" + block + "\n"
    if new != text:
        note.write_text(new, encoding="utf-8")


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nodes", default="", help="comma list of node ids (default: all in bank)")
    ap.add_argument("--no-booklets", action="store_true")
    args = ap.parse_args()
    only = {int(x) for x in args.nodes.split(",") if x.strip()} if args.nodes else None

    by_node: dict[int, list[dict]] = {}
    for e in load_bank():
        for nid in e.get("topic_node_ids") or []:
            by_node.setdefault(int(nid), []).append(e)

    PRACTICE.mkdir(exist_ok=True)
    BOOKLETS.mkdir(parents=True, exist_ok=True)
    made = linked = 0
    for num in sorted(by_node):
        if only and num not in only:
            continue
        entries = sorted(by_node[num], key=sort_key)
        note = note_for(num)
        name = note.stem.split(" - ", 1)[1] if note else f"node {num}"
        (PRACTICE / f"{num} - Practice.md").write_text(
            build_note(num, name, entries), encoding="utf-8")
        if not args.no_booklets:
            build_booklet(num, name, entries, BOOKLETS / f"{num} - Booklet.pdf")
        if note:
            link_exercise_note(note, num, len(entries))
            linked += 1
        else:
            print(f"WARN: node {num}: no exercise note found (practice note still written)")
        made += 1
    print(f"Generated {made} practice notes"
          + ("" if args.no_booklets else " + booklets")
          + f", linked {linked} exercise notes -> {PRACTICE}")


if __name__ == "__main__":
    main()
