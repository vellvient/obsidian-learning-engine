#!/usr/bin/env python3
"""
sprint_status.py — report real progress vs 2-week sprint plan tables.

Does NOT rewrite the sprint files (manual status columns are user-facing).
Prints a status report so you can update ⬜/🔄/✅ deliberately.

Usage:
  python scripts/sprint_status.py
"""

from __future__ import annotations
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")
import re
import sys
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
SPRINTS = sorted(VAULT.glob("00 - *Sprint*.md"))


def exercise_progress(eid: int):
    for fp in VAULT.glob(f"{eid} - *.md"):
        text = fp.read_text(encoding="utf-8", errors="replace")
        boxes = re.findall(r"^- \[[ xX]\]", text, re.M)
        ticked = re.findall(r"^- \[[xX]\]", text, re.M)
        total = len(boxes)
        done = len(ticked)
        m = re.search(r"^mastery:\s*(\S+)", text, re.M)
        mastery = m.group(1) if m else "?"
        return done, total, mastery, fp.name
    return None


def main():
    print("=== SPRINT STATUS (checkbox truth) ===\n")
    for sp in SPRINTS:
        if not sp.exists():
            continue
        text = sp.read_text(encoding="utf-8", errors="replace")
        ids = [int(x) for x in re.findall(r"\[\[(\d+)\s*-", text)]
        # unique preserve order
        seen = set()
        uniq = []
        for i in ids:
            if i not in seen:
                seen.add(i)
                uniq.append(i)
        done_ex = prog_ex = none_ex = 0
        rows = []
        for eid in uniq:
            pr = exercise_progress(eid)
            if not pr:
                none_ex += 1
                rows.append((eid, "MISSING", "", ""))
                continue
            d, t, mastery, name = pr
            if t == 0:
                status = "empty"
            elif d == 0:
                status = "⬜"
                none_ex += 1
            elif d >= t:
                status = "✅"
                done_ex += 1
            else:
                status = f"🔄 {d}/{t}"
                prog_ex += 1
            rows.append((eid, status, mastery, f"{d}/{t}"))
        print(f"## {sp.name}")
        print(f"  exercises linked: {len(uniq)} | ✅ {done_ex} | 🔄 {prog_ex} | ⬜/missing {none_ex}")
        print("  Top unfinished:")
        shown = 0
        for eid, status, mastery, frac in rows:
            if status.startswith("✅"):
                continue
            print(f"    #{eid:<4} {status:<10} mastery={mastery:<12} {frac}")
            shown += 1
            if shown >= 15:
                break
        print()
    print("Update sprint tables manually: ⬜ → 🔄 n/m → ✅ when done.")


if __name__ == "__main__":
    main()
