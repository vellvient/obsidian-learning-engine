#!/usr/bin/env python3
"""latexify_answers.py — rewrite bank final_answers as Obsidian-renderable LaTeX.

Collects the distinct final_answers strings from papers/question_bank.json that
look like math but carry no $...$ markup, chunks them, and drives an agent CLI
(any agent CLI; the reference setup used `hermes -z` with a DeepSeek-class`r`nmodel - swap the invocation in run_chunk(), see this directory's README) to rewrite each
as inline LaTeX. Results are merged into papers/answers_tex.json keyed by
entry id — the bank itself is never modified, so merge_bank.py reruns are safe.

Usage (from vault root):
  python scripts/paper_pipeline/latexify_answers.py --pilot   # first chunk only
  python scripts/paper_pipeline/latexify_answers.py           # all chunks
  python scripts/paper_pipeline/latexify_answers.py --merge-only
"""
from __future__ import annotations
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

VAULT = Path(__file__).resolve().parents[2]
BANK = VAULT / "papers" / "question_bank.json"
OUT = VAULT / "papers" / "answers_tex.json"
WORK = VAULT / ".engine" / "paper_mining" / "latex"
CHUNK = 300
TIMEOUT = 900

SKIP_RE = re.compile(r"UNCLEAR|^\s*$")
MATHY_RE = re.compile(r"[=^_\\/<>±√∫Σπθ°²³-]|\d")

PROMPT = (
    "You are running a batch text-conversion job. Steps, in order:\n"
    "1. Read the file .engine/paper_mining/latex/{chunk}.json - a JSON array of "
    "objects {{\"i\": <int>, \"s\": <string>}}. Each s is a final answer to a maths "
    "exam question, extracted from a PDF (may contain scrambled or plain-text math).\n"
    "2. For EVERY object, rewrite s as clean Markdown with all mathematical content "
    "in inline LaTeX delimited by single dollar signs, e.g. '$x = \\\\frac{{3}}{{4}}$ or "
    "$x = -2$'. Keep surrounding prose words as plain text. Fix obvious PDF-extraction "
    "scrambling when the intended math is unambiguous; otherwise keep the content as-is "
    "inside $...$. Do not add explanations, do not change mathematical meaning, do not "
    "solve anything.\n"
    "3. Write the complete result to .engine/paper_mining/latex/{chunk}_result.json - "
    "file content must be ONLY a JSON array of {{\"i\": <int>, \"tex\": <string>}} with "
    "exactly one object per input, same i values.\n"
    "Do not modify any other file."
)


def collect() -> list[str]:
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    strings = []
    seen = set()
    for e in bank:
        for a in e.get("final_answers") or []:
            if not a or SKIP_RE.search(a) or "$" in a or not MATHY_RE.search(a):
                continue
            if a not in seen:
                seen.add(a)
                strings.append(a)
    return strings


def run_chunk(cid: str) -> bool:
    exe = shutil.which("hermes")
    if not exe:
        sys.exit("hermes CLI not found on PATH")
    prompt = PROMPT.format(chunk=cid)
    expected = json.loads((WORK / f"{cid}.json").read_text(encoding="utf-8"))
    for attempt in (1, 2):
        t0 = time.time()
        proc = subprocess.Popen([exe, "-z", prompt], cwd=VAULT,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            proc.communicate(timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            # On Windows, killing only hermes.exe leaves its Python child alive,
            # consuming quota and racing the retry. Kill the whole tree.
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                               capture_output=True)
            else:
                proc.kill()
            proc.communicate()
            print(f"  {cid}: attempt {attempt} timed out")
            continue
        rf = WORK / f"{cid}_result.json"
        ok, msg = validate(rf, expected)
        print(f"  {cid}: attempt {attempt} [{time.time()-t0:.0f}s] -> "
              f"{'OK' if ok else 'FAIL'}: {msg}")
        if ok:
            return True
        rf.unlink(missing_ok=True)
    return False


def validate(rf: Path, expected: list) -> tuple[bool, str]:
    if not rf.exists():
        return False, "result not written"
    try:
        data = json.loads(rf.read_text(encoding="utf-8", errors="replace"))
    except Exception as ex:
        return False, f"bad JSON: {ex}"
    if not isinstance(data, list):
        return False, "not an array"
    idx = {d.get("i") for d in data if isinstance(d, dict) and d.get("tex")}
    want = {d["i"] for d in expected}
    got = len(idx & want)
    if got < 0.9 * len(want):
        return False, f"only {got}/{len(want)} covered"
    withtex = sum(1 for d in data if isinstance(d, dict) and "$" in str(d.get("tex", "")))
    if withtex < 0.7 * len(data):
        return False, f"only {withtex}/{len(data)} contain $ math"
    return True, f"{got}/{len(want)} covered, {withtex} with $"


def merge():
    """string -> tex from all chunk results, then id -> [tex finals] map."""
    s2t = {}
    for rf in sorted(WORK.glob("chunk_*_result.json")):
        cid = rf.name.replace("_result.json", "")
        src = {d["i"]: d["s"] for d in
               json.loads((WORK / f"{cid}.json").read_text(encoding="utf-8"))}
        try:
            for d in json.loads(rf.read_text(encoding="utf-8", errors="replace")):
                if isinstance(d, dict) and d.get("tex") and d.get("i") in src:
                    s2t[src[d["i"]]] = str(d["tex"]).strip()
        except Exception as ex:
            print(f"WARN: {rf.name}: {ex}")
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    out = {}
    for e in bank:
        finals = e.get("final_answers") or []
        tex = [s2t.get(a) for a in finals]
        if any(tex):
            out[e["id"]] = [t if t else (a or "") for t, a in zip(tex, finals)]
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"answers_tex.json: {len(out)} entries with LaTeX finals "
          f"({len(s2t)} distinct strings converted)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", action="store_true", help="run only the first chunk")
    ap.add_argument("--merge-only", action="store_true")
    ap.add_argument("--workers", type=int, default=1, help="concurrent hermes calls")
    args = ap.parse_args()

    WORK.mkdir(parents=True, exist_ok=True)
    if args.merge_only:
        merge()
        return

    strings = collect()
    print(f"{len(strings)} distinct convertible final_answers strings")
    chunks = [strings[i:i + CHUNK] for i in range(0, len(strings), CHUNK)]
    for n, ch in enumerate(chunks, 1):
        cid = f"chunk_{n:03d}"
        f = WORK / f"{cid}.json"
        if not f.exists():
            f.write_text(json.dumps(
                [{"i": i, "s": s} for i, s in enumerate(ch)],
                ensure_ascii=False, indent=0), encoding="utf-8")

    todo = [f"chunk_{n:03d}" for n in range(1, len(chunks) + 1)]
    if args.pilot:
        todo = todo[:1]

    def job(cid: str) -> bool:
        if (WORK / f"{cid}_result.json").exists():
            ok, msg = validate(WORK / f"{cid}_result.json",
                               json.loads((WORK / f"{cid}.json").read_text(encoding="utf-8")))
            if ok:
                print(f"  {cid}: existing result valid -> {msg}")
                return True
        return run_chunk(cid)

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        done = sum(ex.map(job, todo))
    print(f"chunks done: {done}/{len(todo)}")
    merge()


if __name__ == "__main__":
    main()
