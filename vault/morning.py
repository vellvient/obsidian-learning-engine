#!/usr/bin/env python3
"""
morning.py — single morning entrypoint for the math vault.

Runs:
  1. study_today (flow zone × unlock leverage)
  2. FSRS due / legacy backlog stats
  3. regenerates Review Grader + SRS Tracker
  4. micro-schema bridge suggestions
  5. weak-spot boosts from 00 - Weak Spots Priority.md + Error Log

Usage (from vault root):
  python morning.py
  python morning.py --top 10
"""
from __future__ import annotations
import re
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")
from pathlib import Path

VAULT = Path(__file__).resolve().parent


def run(cmd: list) -> int:
    print(f"\n$ {' '.join(cmd)}")
    return subprocess.call(cmd, cwd=str(VAULT))


def parse_weak_spot_ids() -> list:
    ids = []
    for name in ("00 - Weak Spots Priority.md", "00 - Error Log.md"):
        p = VAULT / name
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        # [[387 - ...]] or bare #387 or exercise 387
        for m in re.finditer(r"\[\[(\d+)\s*-", text):
            ids.append(int(m.group(1)))
        for m in re.finditer(r"(?:#|exercise\s+)(\d{2,4})\b", text, re.I):
            ids.append(int(m.group(1)))
    # preserve order, unique
    seen = set()
    out = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def main():
    top = 12
    if "--top" in sys.argv:
        try:
            top = int(sys.argv[sys.argv.index("--top") + 1])
        except Exception:
            pass

    print("=" * 64)
    print("  MORNING — Math Vault 2-sigma loop")
    print("=" * 64)

    # 1) Study today
    run([sys.executable, "study_today.py", "--top", str(top), "--frontier"])

    # 2) FSRS stats + due
    run([sys.executable, "srs_fsrs.py", "--stats"])
    run([sys.executable, "srs_fsrs.py", "--due"])

    # 3) Regenerate grader + tracker
    run([sys.executable, "srs_fsrs.py", "--grader-note"])
    run([sys.executable, "srs_fsrs.py", "--tracker"])

    # 4) Micro-schema bridge
    run([sys.executable, "micro_bridge.py"])

    # 5) Weak spots
    weak = parse_weak_spot_ids()
    print("\n=== WEAK SPOTS (from notes) ===")
    if weak:
        print("  Prioritise if also in flow zone:", ", ".join(f"#{i}" for i in weak[:15]))
    else:
        print("  (no exercise IDs parsed from Weak Spots / Error Log)")

    print("\n" + "=" * 64)
    print("TODAY ORDER:")
    print("  1. Open 00 - Review Grader.md → grade 20–30 oldest (Again if shaky)")
    print("  2. Finish in-progress (see study_today * marks)")
    print("  3. Do top 2 study_today flow-zone items")
    print("  4. 5–10 min micro_trainer (suggested cmds above)")
    print("  5. Evening: python evening.py")
    print("=" * 64)


if __name__ == "__main__":
    main()
