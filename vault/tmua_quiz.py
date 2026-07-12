#!/usr/bin/env python3
"""Interactive TMUA past-paper serving loop.

Selects unseen questions from papers/tmua_question_bank.json, optionally by
graph node or paper. Opens the original question crop, reveals the keyed answer
and worked-solution crop, then records a self-grade in papers/quiz_log.json.

Usage:
  python tmua_quiz.py --count 5
  python tmua_quiz.py --node 123 --count 10
  python tmua_quiz.py --paper 2 --count 10
  python tmua_quiz.py --stats
  python tmua_quiz.py --reset-history
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

VAULT = Path(__file__).resolve().parent
BANK = VAULT / "papers" / "tmua_question_bank.json"
RENDERS = VAULT / "papers" / "renders"
LOG = VAULT / "papers" / "quiz_log.json"


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def node_names() -> dict[int, str]:
    out = {}
    for path in VAULT.glob("[0-9]* - *.md"):
        match = re.match(r"(\d+) - (.*)\.md$", path.name)
        if match:
            out[int(match.group(1))] = match.group(2)
    return out


def open_file(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        if os.name == "nt":
            os.startfile(str(path))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
        return True
    except Exception as ex:
        print(f"  could not open {path.name}: {ex}")
        return False


def question_render(entry_id: str) -> Path:
    return RENDERS / f"{entry_id}.png"


def worked_renders(entry_id: str) -> list[Path]:
    return sorted(RENDERS.glob(f"{entry_id}_wa_p*.png"),
                  key=lambda p: int(p.stem.rsplit("_p", 1)[1]))


def save_log(items: list[dict]) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text(json.dumps(items[-10000:], indent=1), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--node", type=int)
    parser.add_argument("--paper", type=int, choices=[1, 2])
    parser.add_argument("--include-seen", action="store_true")
    parser.add_argument("--stats", action="store_true")
    parser.add_argument("--reset-history", action="store_true")
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()

    history = load_json(LOG, [])
    if args.reset_history:
        save_log([])
        print("TMUA quiz history reset.")
        return
    if args.stats:
        counts = Counter(x.get("grade") for x in history)
        print(f"quiz history: {len(history)} attempts ({dict(counts)})")
        return
    if not BANK.exists():
        sys.exit("No TMUA question bank found - run scripts/tmua_pipeline.py first.")

    bank = load_json(BANK, [])
    if args.node is not None:
        bank = [q for q in bank if args.node in q.get("topic_node_ids", [])]
    if args.paper is not None:
        bank = [q for q in bank if q.get("paper") == args.paper]
    if not args.include_seen:
        seen = {x.get("id") for x in history if x.get("grade") != "skip"}
        bank = [q for q in bank if q.get("id") not in seen]
    if not bank:
        sys.exit("No matching unseen questions. Use --include-seen or --reset-history.")

    random.Random(args.seed).shuffle(bank)
    chosen = bank[:max(1, args.count)]
    names = node_names()
    session = []
    print(f"=== TMUA QUIZ: {len(chosen)} questions ===")

    for index, q in enumerate(chosen, 1):
        tags = ", ".join(f"{n}: {names.get(n, '?')}" for n in q.get("topic_node_ids", []))
        print(f"\n--- {index}/{len(chosen)}  {q['id']}  Paper {q['paper']}  [{q.get('difficulty','?')}]" )
        print(f"  skills: {tags}")
        qpath = question_render(q["id"])
        if not open_file(qpath):
            print(f"  question image: {qpath}")
        input("  attempt it, then press Enter to reveal...")

        print(f"  ANSWER: {q.get('answer', '?')}")
        worked = worked_renders(q["id"])
        if worked:
            for path in worked:
                open_file(path)
        else:
            print("  no worked-solution crop; use the keyed answer above.")

        grade = input("  grade [c]orrect / [w]rong / [s]kip / [q]uit: ").strip().lower()[:1]
        if grade == "q":
            break
        label = {"c": "correct", "w": "wrong", "s": "skip"}.get(grade, "skip")
        row = {
            "id": q["id"], "paper": q["paper"], "nodes": q.get("topic_node_ids", []),
            "grade": label, "ts": datetime.now().isoformat(timespec="seconds")
        }
        history.append(row)
        session.append(row)
        save_log(history)

    counts = Counter(x["grade"] for x in session)
    print(f"\nSession: {len(session)} attempted - {dict(counts)}")
    if counts.get("wrong"):
        print("Review the worked solutions now; repeat wrong questions next session with --include-seen.")


if __name__ == "__main__":
    main()
