#!/usr/bin/env python3
"""tmua_pipeline.py — topical past-paper system for the TMUA vault.

Sources (UAT-UK official releases, NOT in git):
  Set `TMUA_PDF_DIR` to a folder containing:
    {sitting}_TMUA_Paper{1,2}.pdf            20 MCQs, one question per page
    {sitting}_TMUA_AnswerKey.pdf             letter key for both papers
    {sitting}_TMUA_Paper{n}_WorkedAnswers.pdf full worked solutions per question

Pipeline (run from the TMUA vault root):
  python scripts/tmua_pipeline.py --extract    # PDFs -> papers/extracted/*.json
  python scripts/tmua_pipeline.py --batches    # bundle for the tagging model
  python scripts/tmua_pipeline.py --merge      # results -> papers/tmua_question_bank.json
  python scripts/tmua_pipeline.py --render     # question + worked-answer PNG crops
  python scripts/tmua_pipeline.py --practice   # per-node notes + booklets + links

Notes:
  * 2016/2017 papers use obfuscated fonts (unreadable text) — the tagging text
    for those questions is taken from the worked solutions instead (clean).
  * Question N lives on page N+1 of the paper; the leading page number is used
    as authority when extractable.
  * Everything under papers/ is gitignored (copyrighted exam content).
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import fitz  # PyMuPDF

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

VAULT = Path(__file__).resolve().parents[1]
SRC = Path(os.environ.get("TMUA_PDF_DIR", "path/to/your/TMUA_PDFs"))
PAPERS = VAULT / "papers"
EXTRACTED = PAPERS / "extracted"
RENDERS = PAPERS / "renders"
BOOKLETS = PAPERS / "booklets"
PRACTICE = VAULT / "practice"
BANK = PAPERS / "tmua_question_bank.json"
MINING = VAULT / ".engine" / "paper_mining"

N_Q = 20
MARK_START = "<!-- auto:practice-link -->"
MARK_END = "<!-- /auto:practice-link -->"


def sittings() -> list[str]:
    """Sitting prefixes. 2016 is EXCLUDED: its papers are 16 pages for 20
    questions (multi-question pages + obfuscated fonts) — not extractable with
    the one-question-per-page layout every other sitting uses."""
    out = []
    for f in sorted(SRC.glob("*Paper1.pdf")):
        prefix = f.name.replace("_TMUA_Paper1.pdf", "").replace("_Paper1.pdf", "")
        if prefix != "2016":
            out.append(prefix)
    return out


def paper_path(sitting: str, paper: int, worked: bool = False) -> Path:
    suffix = f"Paper{paper}_WorkedAnswers.pdf" if worked else f"Paper{paper}.pdf"
    for name in (f"{sitting}_TMUA_{suffix}", f"{sitting}_{suffix}"):
        p = SRC / name
        if p.exists():
            return p
    return SRC / f"{sitting}_TMUA_{suffix}"


def sit_slug(sitting: str) -> str:
    return "spec" if "Specimen" in sitting else sitting


def clean_ratio(text: str) -> float:
    if not text:
        return 0.0
    ok = sum(1 for ch in text if ch.isalnum() or ch.isspace() or ch in ".,()=+-<>/^{}[]?!:;'\"")
    return ok / len(text)


# ------------------------------------------------------------------- extract

def parse_answer_key(sitting: str) -> tuple[dict, dict]:
    """-> ({qnum: letter} paper1, {qnum: letter} paper2)."""
    f = SRC / f"{sitting}_TMUA_AnswerKey.pdf"
    if not f.exists():
        f = SRC / f"{sitting}_AnswerKey.pdf"
    doc = fitz.open(f)
    text = " ".join(doc[p].get_text() for p in range(doc.page_count))
    doc.close()
    text = text.replace("\xa0", " ")
    rows = re.findall(r"(\d{1,2})\s+([A-H])\s+(\d{1,2})\s+([A-H])", text)
    p1, p2 = {}, {}
    for q1, k1, q2, k2 in rows:
        p1[int(q1)] = k1
        p2[int(q2)] = k2
    if len(p1) < N_Q or len(p2) < N_Q:
        # fallback: two sequential blocks of 20 (some years lay out per-paper)
        pairs = re.findall(r"(\d{1,2})\s+([A-H])", text)
        seq = [(int(q), k) for q, k in pairs]
        if len(seq) >= 2 * N_Q:
            p1 = dict(seq[:N_Q])
            p2 = dict(seq[N_Q:2 * N_Q])
    return p1, p2


def split_worked(sitting: str, paper: int) -> dict[int, list[int]]:
    """qnum -> [page indexes] in the worked-answers PDF."""
    f = paper_path(sitting, paper, worked=True)
    if not f.exists():
        return {}
    doc = fitz.open(f)
    starts = {}
    for pi in range(doc.page_count):
        lines = [l.strip() for l in doc[pi].get_text().split("\n") if l.strip()]
        for l in lines[:4]:
            m = re.match(r"^Question (\d{1,2})$", l)
            if m:
                starts[pi] = int(m.group(1))
                break
    pages: dict[int, list[int]] = defaultdict(list)
    current = None
    for pi in range(doc.page_count):
        if pi in starts:
            current = starts[pi]
        if current is not None:
            pages[current].append(pi)
    doc.close()
    return dict(pages)


def worked_text(sitting: str, paper: int, pages: list[int]) -> str:
    f = paper_path(sitting, paper, worked=True)
    doc = fitz.open(f)
    chunks = []
    for pi in pages[:2]:
        t = doc[pi].get_text()
        # drop the running header + Question heading
        t = re.sub(r"^.*Solutions\s*\n", "", t)
        t = re.sub(r"^\s*Question \d+\s*\n", "", t)
        chunks.append(t.strip())
    doc.close()
    return "\n".join(chunks)[:900]


def extract_paper(sitting: str, paper: int, key: dict) -> dict | None:
    f = paper_path(sitting, paper)
    if not f.exists():
        return None
    doc = fitz.open(f)
    worked = split_worked(sitting, paper)
    questions = []
    # map qnum -> page: leading page number when extractable, else page = q+1
    page_of = {}
    for pi in range(doc.page_count):
        t = doc[pi].get_text().strip()
        m = re.match(r"^(\d{1,2})\b", t)
        if m and 1 <= int(m.group(1)) <= N_Q and clean_ratio(t) > 0.6:
            page_of.setdefault(int(m.group(1)), pi)
    fallback = len(page_of) < N_Q // 2
    for q in range(1, N_Q + 1):
        pi = page_of.get(q, q + 1)
        if pi >= doc.page_count:
            continue
        text = doc[pi].get_text().strip()
        readable = clean_ratio(text) > 0.6 and len(text) > 60
        tag_text = text[:900] if readable else None
        if not tag_text and worked.get(q):
            tag_text = "(from worked solution) " + worked_text(sitting, paper, worked[q])
        questions.append({
            "qnum": q,
            "page": pi,
            "text": tag_text or "",
            "text_source": "paper" if readable else "worked",
            "answer": key.get(q),
            "worked_pages": worked.get(q, []),
        })
    doc.close()
    slug = sit_slug(sitting)
    return {
        "paper_id": f"tmua_{slug}_p{paper}",
        "sitting": slug,
        "paper": paper,
        "source_pdf": str(f),
        "worked_pdf": str(paper_path(sitting, paper, worked=True)),
        "page_mapping": "detected" if not fallback else "q+1 fallback",
        "n_questions": len(questions),
        "questions": questions,
    }


def cmd_extract():
    EXTRACTED.mkdir(parents=True, exist_ok=True)
    n = 0
    for sitting in sittings():
        k1, k2 = parse_answer_key(sitting)
        for paper, key in ((1, k1), (2, k2)):
            data = extract_paper(sitting, paper, key)
            if not data:
                continue
            out = EXTRACTED / f"{data['paper_id']}.json"
            out.write_text(json.dumps(data, indent=1), encoding="utf-8")
            keyed = sum(1 for q in data["questions"] if q["answer"])
            src_worked = sum(1 for q in data["questions"] if q["text_source"] == "worked")
            print(f"{data['paper_id']}: {data['n_questions']} q, {keyed} keyed, "
                  f"{src_worked} tagged-from-worked, mapping={data['page_mapping']}")
            n += 1
    print(f"extracted {n} papers -> {EXTRACTED}")


# ------------------------------------------------------------------- batches

def topic_index() -> str:
    lines = []
    for f in sorted(VAULT.glob("*.md")):
        m = re.match(r"^(\d+)\s*-\s*(.+)\.md$", f.name)
        if not m:
            continue
        num, name = int(m.group(1)), m.group(2)
        subs = re.findall(r"^- \[[ x]\] \d+[a-z]: (.+)$",
                          f.read_text(encoding="utf-8", errors="replace"), re.MULTILINE)
        lines.append(f"{num}: {name}" + (f" [{'; '.join(s[:60] for s in subs[:3])}]" if subs else ""))
    return "\n".join(lines)


SYSTEM_PROMPT = """You are tagging TMUA (Test of Mathematics for University Admission) multiple-choice questions to a knowledge-graph topic index.

For EVERY question in the batch, output one entry:
{"id": "<question id exactly as given>", "topic_node_ids": [<1-3 node ids>], "difficulty": "easy"|"medium"|"hard"}

Rules:
1. topic_node_ids come ONLY from the topic index provided in the batch. Pick the 1-3 most specific nodes the question actually tests (not merely mentions).
2. Paper 2 questions often test logic/proof nodes (120-136) IN ADDITION to a maths node - tag both when true.
3. difficulty is judged for a strong A-level student under TMUA time pressure.
4. Some question texts are taken from the worked solution (marked as such) - infer the tested topics from the solution's reasoning.
5. Output ONLY the JSON array, nothing else. One entry per question, ids exactly as given.
"""


def cmd_batches(per_batch: int = 60):
    MINING.mkdir(parents=True, exist_ok=True)
    (MINING / "results").mkdir(exist_ok=True)
    (MINING / "system_prompt.txt").write_text(SYSTEM_PROMPT, encoding="utf-8")
    idx = topic_index()
    entries = []
    for f in sorted(EXTRACTED.glob("tmua_*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        for q in data["questions"]:
            if not q["text"]:
                continue
            entries.append({"id": f"{data['paper_id']}_q{q['qnum']}",
                            "paper": data["paper_id"], "text": q["text"]})
    batches = [entries[i:i + per_batch] for i in range(0, len(entries), per_batch)]
    for n, b in enumerate(batches, 1):
        (MINING / f"batch_{n:02d}.json").write_text(json.dumps(
            {"batch_id": f"batch_{n:02d}", "topic_index": idx, "questions": b},
            ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{len(entries)} questions -> {len(batches)} batches in {MINING}")
    print("Process each with your agent CLI, e.g.:")
    print('  hermes -z "Read .engine/paper_mining/system_prompt.txt then '
          '.engine/paper_mining/batch_01.json; apply the rules to EVERY question; '
          'write ONLY the JSON array to .engine/paper_mining/results/batch_01_result.json"')


# --------------------------------------------------------------------- merge

def cmd_merge():
    tags = {}
    for rf in sorted((MINING / "results").glob("batch_*_result.json")):
        try:
            for d in json.loads(rf.read_text(encoding="utf-8", errors="replace")):
                if isinstance(d, dict) and d.get("id"):
                    tags[d["id"]] = d
        except Exception as ex:
            print(f"WARN {rf.name}: {ex}")
    bank = []
    for f in sorted(EXTRACTED.glob("tmua_*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        for q in data["questions"]:
            qid = f"{data['paper_id']}_q{q['qnum']}"
            t = tags.get(qid, {})
            bank.append({
                "id": qid, "sitting": data["sitting"], "paper": data["paper"],
                "qnum": q["qnum"], "answer": q["answer"],
                "topic_node_ids": t.get("topic_node_ids") or [],
                "difficulty": t.get("difficulty") or "medium",
            })
    BANK.write_text(json.dumps(bank, indent=1), encoding="utf-8")
    tagged = sum(1 for e in bank if e["topic_node_ids"])
    print(f"bank: {len(bank)} questions, {tagged} tagged ({100 * tagged // max(1, len(bank))}%)")


# -------------------------------------------------------------------- render

def q_png(qid: str) -> Path:
    return RENDERS / f"{qid}.png"


def worked_pngs(qid: str) -> list[Path]:
    return sorted(RENDERS.glob(f"{qid}_wa_p*.png"),
                  key=lambda p: int(p.stem.rsplit("_p", 1)[1]))


def cmd_render(force: bool = False):
    RENDERS.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in sorted(EXTRACTED.glob("tmua_*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        doc = fitz.open(data["source_pdf"])
        wdoc = fitz.open(data["worked_pdf"]) if Path(data["worked_pdf"]).exists() else None
        for q in data["questions"]:
            qid = f"{data['paper_id']}_q{q['qnum']}"
            if not force and q_png(qid).exists():
                continue
            page = doc[q["page"]]
            r = page.rect
            clip = fitz.Rect(30, 42, r.width - 30, r.height - 45)  # drop header/footer
            page.get_pixmap(clip=clip, matrix=fitz.Matrix(2, 2)).save(q_png(qid))
            if wdoc:
                for i, wp in enumerate(q["worked_pages"], 1):
                    wr = wdoc[wp].rect
                    wclip = fitz.Rect(30, 55, wr.width - 30, wr.height - 40)
                    wdoc[wp].get_pixmap(clip=wclip, matrix=fitz.Matrix(2, 2)).save(
                        RENDERS / f"{qid}_wa_p{i}.png")
            n += 1
        doc.close()
        if wdoc:
            wdoc.close()
    print(f"rendered {n} questions (+ worked answers) -> {RENDERS}")


# ------------------------------------------------------------------ practice

DIFF_RANK = {"easy": 0, "medium": 1, "hard": 2}


def note_for(num: int) -> Path | None:
    hits = [p for p in VAULT.glob(f"{num} - *.md") if p.is_file()]
    return hits[0] if hits else None


def build_note(num: int, name: str, entries: list[dict]) -> str:
    lines = [
        "---", "tags: [practice]", "auto: true", f"node: {num}",
        f"generated: {dt.date.today().isoformat()}", "---", "",
        f"# {num} — Practice: {name}", "",
        f"**{len(entries)} tagged TMUA questions** (easy → hard) · "
        f"printable: [[papers/booklets/{num} - Booklet.pdf|booklet]]", "",
        f"Node: [[{num} - {name}]]", "",
        "> AUTO-GENERATED by tmua_pipeline.py — do not hand-edit.", "",
    ]
    for i, e in enumerate(entries, 1):
        lines += ["---", "",
                  f"## Q{i} · {e['id']} · {e.get('difficulty', '?')}", ""]
        if q_png(e["id"]).exists():
            lines.append(f"![[papers/renders/{q_png(e['id']).name}]]")
        lines += ["", "> [!success]- Answer & worked solution",
                  f"> **Answer: {e.get('answer') or '?'}**"]
        for p in worked_pngs(e["id"]):
            lines.append(f"> ![[papers/renders/{p.name}]]")
        lines.append("")
    return "\n".join(lines) + "\n"


def build_booklet(num: int, name: str, entries: list[dict], out: Path):
    a4 = fitz.paper_rect("a4")
    MARGIN, TOP, BOTTOM = 36, 45, 40
    doc = fitz.open()
    page = doc.new_page(width=a4.width, height=a4.height)
    page.insert_text((72, 120), f"{num} - {name}"[:80], fontsize=18)
    page.insert_text((72, 145), f"{len(entries)} TMUA questions, easy -> hard. "
                                f"Answer + worked solution follows each question.", fontsize=11)
    y = a4.height

    def new_page(header):
        nonlocal page, y
        page = doc.new_page(width=a4.width, height=a4.height)
        y = TOP
        page.insert_text((MARGIN, 30), header, fontsize=9, color=(0.35, 0.35, 0.35))

    def place(png: Path, header: str):
        nonlocal y
        pix = fitz.Pixmap(str(png))
        scale = min((a4.width - 2 * MARGIN) / pix.width, 1.0)
        w, h = pix.width * scale, pix.height * scale
        max_h = a4.height - TOP - BOTTOM
        if h > max_h:
            w, h = w * max_h / h, max_h
        if y + h > a4.height - BOTTOM:
            new_page(header + "  (cont.)")
        page.insert_image(fitz.Rect(MARGIN, y, MARGIN + w, y + h), pixmap=pix)
        y += h + 8

    for i, e in enumerate(entries, 1):
        header = f"Q{i}  |  {e['id']}  |  {e.get('difficulty', '?')}"
        new_page(header)
        if q_png(e["id"]).exists():
            place(q_png(e["id"]), header)
        if y + 24 > a4.height - BOTTOM:
            new_page(header + " (answer)")
        page.draw_line(fitz.Point(MARGIN, y + 2), fitz.Point(a4.width - MARGIN, y + 2),
                       color=(0.6, 0.6, 0.6), width=0.6)
        page.insert_text((MARGIN, y + 16), f"Answer: {e.get('answer') or '?'}",
                         fontsize=11, color=(0.2, 0.45, 0.2))
        y += 26
        for p in worked_pngs(e["id"]):
            place(p, header)
    doc.save(out, deflate=True)
    doc.close()


def link_note(note: Path, num: int, n_q: int):
    block = (f"{MARK_START}\n## 📄 TMUA Past-Paper Practice\n"
             f"[[{num} - Practice|{n_q} tagged questions]] · "
             f"[[papers/booklets/{num} - Booklet.pdf|booklet]]\n{MARK_END}")
    text = note.read_text(encoding="utf-8")
    if MARK_START in text:
        new = re.sub(re.escape(MARK_START) + r".*?" + re.escape(MARK_END),
                     block, text, flags=re.S)
    else:
        new = text.rstrip("\n") + "\n\n" + block + "\n"
    if new != text:
        note.write_text(new, encoding="utf-8")


def cmd_practice(nodes: set[int] | None, booklets: bool = True):
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    by_node: dict[int, list[dict]] = defaultdict(list)
    for e in bank:
        for nid in e.get("topic_node_ids") or []:
            by_node[int(nid)].append(e)
    PRACTICE.mkdir(exist_ok=True)
    BOOKLETS.mkdir(parents=True, exist_ok=True)
    made = 0
    for num in sorted(by_node):
        if nodes and num not in nodes:
            continue
        entries = sorted(by_node[num],
                         key=lambda e: (DIFF_RANK.get(e.get("difficulty"), 1), e["sitting"]))
        note = note_for(num)
        name = note.stem.split(" - ", 1)[1] if note else f"node {num}"
        (PRACTICE / f"{num} - Practice.md").write_text(
            build_note(num, name, entries), encoding="utf-8")
        if booklets:
            build_booklet(num, name, entries, BOOKLETS / f"{num} - Booklet.pdf")
        if note:
            link_note(note, num, len(entries))
        made += 1
    print(f"generated {made} practice notes{' + booklets' if booklets else ''} -> {PRACTICE}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--extract", action="store_true")
    ap.add_argument("--batches", action="store_true")
    ap.add_argument("--merge", action="store_true")
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--practice", action="store_true")
    ap.add_argument("--nodes", default="", help="comma list for --practice")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-booklets", action="store_true")
    args = ap.parse_args()
    if args.extract:
        cmd_extract()
    if args.batches:
        cmd_batches()
    if args.merge:
        cmd_merge()
    if args.render:
        cmd_render(args.force)
    if args.practice:
        only = {int(x) for x in args.nodes.split(",") if x.strip()} or None
        cmd_practice(only, booklets=not args.no_booklets)
    if not any([args.extract, args.batches, args.merge, args.render, args.practice]):
        main.__doc__ = __doc__
        print(__doc__)


if __name__ == "__main__":
    main()
