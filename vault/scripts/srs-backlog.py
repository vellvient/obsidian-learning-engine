#!/usr/bin/env python3
"""Compute the overdue SRS backlog from .obsidian/srs_state.json.

The Flow Zone Diagnostic truncates its "SRS Due Today" table at
"... and N more", so it cannot be trusted for the real backlog.
This script parses the state file directly.

Usage:
    python srs-backlog.py [path-to-srs_state.json] [YYYY-MM-DD as 'today']

Prints:
    - total overdue review stage-entries and unique skills
    - overdue stage-entries grouped by ORIGINAL tick (study) date
    - overdue stage-entries + unique skills grouped by DUE date (oldest first)
Use the due-date buckets to triage the oldest cohort first.
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

import json
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime

DEFAULT = str(Path(__file__).resolve().parents[1] / ".obsidian" / "srs_state.json")


def parse_dt(s):
    return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    if len(sys.argv) > 2:
        t = datetime.strptime(sys.argv[2], "%Y-%m-%d")
    else:
        t = datetime.now()
    cutoff = datetime(t.year, t.month, t.day, 23, 59)

    with open(path, encoding="utf-8", errors="replace") as f:
        data = json.load(f)
    reviews = data.get("reviews", {})

    overdue = []
    for key, r in reviews.items():
        for s in r.get("review_stages", []):
            if "due" in s:
                d = parse_dt(s["due"])
                if d <= cutoff:
                    overdue.append(
                        (r.get("skill", key), s["stage"], d, parse_dt(r["ticked_at"]))
                    )

    skills = sorted({o[0] for o in overdue})
    print(f"Total overdue STAGE-entries: {len(overdue)}")
    print(f"Unique skills with >=1 overdue stage: {len(skills)}")

    by_tick = defaultdict(int)
    for o in overdue:
        by_tick[o[3].date()] += 1
    print("\nOverdue stage-entries by ORIGINAL study/tick date:")
    for d in sorted(by_tick):
        print(f"  {d}: {by_tick[d]}")

    by_due = defaultdict(int)
    by_due_skills = defaultdict(set)
    for o in overdue:
        by_due[o[2].date()] += 1
        by_due_skills[o[2].date()].add(o[0])
    print("\nOverdue stage-entries + unique skills by DUE date (oldest first):")
    for d in sorted(by_due):
        print(f"  {d}: {by_due[d]} entries / {len(by_due_skills[d])} skills")


if __name__ == "__main__":
    main()
