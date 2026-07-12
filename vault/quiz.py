#!/usr/bin/env python3
"""quiz.py — serve past-paper questions from the topical bank, record self-grades.

Picks questions tagged to nodes you should study right now (flow zone + FSRS-due),
opens the question render, lets you attempt on paper, reveals the mark-scheme
crop, and records your self-grade:

  wrong    -> log_error.py <node> "quiz miss ..." --again   (FSRS Again + lock)
  correct  -> grades that node's DUE FSRS subskills Good (cap 3, due-only)
  partial  -> logged only (no FSRS write)

Session log: papers/quiz_log.json (served questions are not repeated).

Usage (from vault root):
  python quiz.py                       # 5 questions from flow-zone/due nodes
  python quiz.py --node 413 617        # specific nodes
  python quiz.py --count 10 --difficulty easy
  python quiz.py --due-only            # only nodes with FSRS-due subskills
  python quiz.py --stats               # session history summary
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

VAULT = Path(__file__).resolve().parent
BANK = VAULT / "papers" / "question_bank.json"
RENDERS = VAULT / "papers" / "renders"
LOG = VAULT / "papers" / "quiz_log.json"

sys.path.insert(0, str(VAULT))
from srs_fsrs import VaultFSRS, Rating  # noqa: E402

ID_RE = re.compile(r"^(.*)_q(\d+)$")
DIFF_RANK = {"easy": 0, "medium": 1, "hard": 2}


def load_log() -> list[dict]:
    if LOG.exists():
        try:
            return json.loads(LOG.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def save_log(log: list[dict]):
    LOG.write_text(json.dumps(log, indent=1), encoding="utf-8")


def renders(entry_id: str, ms: bool = False) -> list[Path]:
    m = ID_RE.match(entry_id)
    if not m:
        return []
    pat = f"{m.group(1)}_ms_q{m.group(2)}_p*.png" if ms else f"{m.group(1)}_q{m.group(2)}_p*.png"
    return sorted(RENDERS.glob(pat), key=lambda p: int(p.stem.rsplit("_p", 1)[1]))


def tex_finals(entry_id: str) -> list[str]:
    f = VAULT / "papers" / "answers_tex.json"
    if not hasattr(tex_finals, "_cache"):
        tex_finals._cache = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    return tex_finals._cache.get(entry_id) or []


def key_num(review_key: str) -> int | None:
    m = re.match(r"^(\d+)\s*-", review_key)
    return int(m.group(1)) if m else None


def node_name(num: int) -> str:
    hits = [p for p in VAULT.glob(f"{num} - *.md") if p.is_file()]
    return hits[0].stem if hits else f"node {num}"


def pick_nodes(args, by_node: dict[int, list]) -> tuple[list[int], dict[int, list[str]]]:
    """Candidate nodes (with bank questions) + due FSRS keys per node."""
    v = VaultFSRS()
    due_by_node: dict[int, list[str]] = defaultdict(list)
    for k in v.due_today():
        n = key_num(k)
        if n:
            due_by_node[n].append(k)

    if args.node:
        return [n for n in args.node if n in by_node], due_by_node

    import flow_diagnostic as diag
    exs, topics = diag.scan_vault()
    d = diag.build_diagnostic(exs, topics)
    flow = [num for num, _ex, _st in d["flow_zone"]]

    candidates: list[int] = []
    for n in flow:                      # flow zone first (ordered by diagnostic)
        if n in by_node and n not in candidates:
            candidates.append(n)
    for n in due_by_node:               # then due nodes not already in flow
        if n in by_node and n not in candidates:
            candidates.append(n)
    if args.due_only:
        candidates = [n for n in candidates if due_by_node.get(n)]
    return candidates, due_by_node


def pick_questions(args, nodes: list[int], by_node: dict[int, list]) -> list[dict]:
    done = {r["id"] for r in load_log()}
    picked, seen = [], set()
    # interleave: one question per node per round, easy->hard within node
    queues = {}
    for n in nodes:
        q = [e for e in sorted(by_node[n], key=lambda e: (DIFF_RANK.get(e.get("difficulty"), 1),
                                                          e.get("marks") or 0))
             if e["id"] not in done and (not args.difficulty or e.get("difficulty") == args.difficulty)]
        if q:
            queues[n] = q
    while len(picked) < args.count and queues:
        for n in list(queues):
            if len(picked) >= args.count:
                break
            while queues[n] and queues[n][0]["id"] in seen:
                queues[n].pop(0)
            if not queues[n]:
                del queues[n]
                continue
            e = queues[n].pop(0)
            seen.add(e["id"])
            picked.append((n, e))
    return picked


def show(path: Path):
    try:
        os.startfile(path)  # Windows default image viewer
    except Exception as ex:
        print(f"  (could not open {path.name}: {ex})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--node", type=int, nargs="*", help="serve specific node ids")
    ap.add_argument("--count", type=int, default=5)
    ap.add_argument("--difficulty", choices=["easy", "medium", "hard"])
    ap.add_argument("--due-only", action="store_true")
    ap.add_argument("--stats", action="store_true")
    args = ap.parse_args()

    log = load_log()
    if args.stats:
        by_grade = defaultdict(int)
        for r in log:
            by_grade[r["grade"]] += 1
        print(f"quiz history: {len(log)} questions "
              f"({dict(by_grade)})")
        return

    if not BANK.exists():
        sys.exit("No question bank found - build one first (docs: paper pipeline; "
                 "run extract/process_batches/merge_bank).")
    by_node: dict[int, list[dict]] = defaultdict(list)
    for e in json.loads(BANK.read_text(encoding="utf-8")):
        for nid in e.get("topic_node_ids") or []:
            by_node[int(nid)].append(e)

    nodes, due_by_node = pick_nodes(args, by_node)
    if not nodes:
        sys.exit("No candidate nodes (try --node N, or check flow zone / due list).")
    picked = pick_questions(args, nodes, by_node)
    if not picked:
        sys.exit("No unseen questions match (all served? try --difficulty or other nodes).")

    print(f"=== QUIZ: {len(picked)} questions from nodes "
          f"{sorted({n for n, _ in picked})} ===\n")
    v = VaultFSRS()
    results = defaultdict(lambda: [0, 0])  # node -> [correct, total]
    missed = 0

    for i, (node, e) in enumerate(picked, 1):
        print(f"--- {i}/{len(picked)}  {e['id']}  [{e.get('difficulty','?')}, "
              f"{e['marks']} marks]  node {node}: {node_name(node)}")
        qr = renders(e["id"])
        if qr:
            for p in qr:
                show(p)
        else:
            print(e.get("question", "")[:600])
        input("  attempt on paper, then press Enter to reveal the answer... ")
        finals = tex_finals(e["id"]) or [a for a in e.get("final_answers") or [] if a]
        if finals:
            print("  FINAL:", " | ".join(finals)[:300])
        msr = renders(e["id"], ms=True)
        if msr:
            for p in msr:
                show(p)
        else:
            for pt in (e.get("markscheme_points") or [])[:6]:
                print("   -", pt[:140])

        while True:
            g = input("  grade [c]orrect / [p]artial / [w]rong / [s]kip / [q]uit: ").strip().lower()
            if g in ("c", "p", "w", "s", "q"):
                break
        if g == "q":
            break
        if g == "s":
            continue
        grade = {"c": "correct", "p": "partial", "w": "wrong"}[g]
        log.append({"id": e["id"], "node": node, "grade": grade,
                    "ts": dt.datetime.now().isoformat(timespec="seconds")})
        save_log(log)
        results[node][1] += 1
        if grade == "correct":
            results[node][0] += 1
            graded = 0
            for k in due_by_node.get(node, [])[:3]:
                if v.grade_review(k, Rating.Good):
                    graded += 1
            if graded:
                v.save()
                print(f"  -> {graded} due FSRS subskill(s) of node {node} graded Good")
        elif grade == "wrong":
            missed += 1
            note = input("  one line on what went wrong (for the error log): ").strip()
            msg = f"quiz miss {e['id']}" + (f" - {note}" if note else "")
            subprocess.run([sys.executable, str(VAULT / "log_error.py"),
                            str(node), msg], cwd=VAULT)
            # grade the node's FSRS cards Again directly (log_error's --again
            # needs a lettered subskill id; a bare node number is a no-op).
            # Due cards first; else the node's first seeded card, so the miss
            # affects scheduling and relearning-lock hides dependents.
            targets = due_by_node.get(node, [])[:3]
            if not targets:
                targets = [k for k in v.state.get("reviews", {})
                           if key_num(k) == node and (v.state["reviews"][k].get("fsrs"))][:1]
            graded = sum(1 for k in targets if v.grade_review(k, Rating.Again))
            if graded:
                v.save()
                print(f"  -> {graded} FSRS subskill(s) of node {node} graded Again (relearning-lock)")
        print()

    print("=== session summary ===")
    for n in sorted(results):
        c, t = results[n]
        print(f"  node {n} ({node_name(n)}): {c}/{t}")
    if missed:
        print(f"{missed} miss(es) logged - run /error-triage in Claude Code to batch-analyse.")


if __name__ == "__main__":
    main()
