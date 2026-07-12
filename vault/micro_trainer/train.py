#!/usr/bin/env python3
"""
train.py
========
CLI for the micro-schema CCT trainer.

Commands
--------
    python train.py --list            List available schemas + mastery %
    python train.py --all             Train all schemas (production mode)
    python train.py --detect          Detection mode (VALID/DISTRACTION)
    python train.py diff_squares ...  Train specific schemas (by id or name)
    python train.py --count 30 ...    Set number of problems

Examples
--------
    python train.py diff_squares perfect_square
    python train.py --detect --count 20
    python train.py --all --count 40
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")


import sys

from micro_trainer import CCTTrainer, load_progress
from schemas_algebra import ALGEBRA_SCHEMAS

BY_ID = {s.id: s for s in ALGEBRA_SCHEMAS}
BY_NAME = {s.name.lower(): s for s in ALGEBRA_SCHEMAS}
DETECT_SCHEMAS = [s for s in ALGEBRA_SCHEMAS if s.detect_items]


def cmd_list() -> None:
    prog = load_progress()
    print("\n  Available algebra micro-schemas")
    print("  " + "-" * 62)
    for s in ALGEBRA_SCHEMAS:
        rec = prog.get(s.id)
        m = f"{rec['mastery']:.0f}%" if rec else "—"
        sess = rec["sessions"] if rec else 0
        tag = " [detect]" if s.detect_items and s.max_level == 0 else ""
        print(f"  [{s.id:<14}] {s.name:<26} mastery {m:>5}  ({sess} sessions){tag}")
    print()


def parse_args(argv: list):
    count = 24
    detect = False
    schemas = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--list":
            return {"list": True}
        elif a == "--detect":
            detect = True
        elif a == "--all":
            schemas.append("__all__")
        elif a == "--count":
            i += 1
            try:
                count = int(argv[i])
            except (IndexError, ValueError):
                pass
        elif a.startswith("--count="):
            try:
                count = int(a.split("=", 1)[1])
            except ValueError:
                pass
        else:
            schemas.append(a)
        i += 1
    return {"count": count, "detect": detect, "schemas": schemas}


def main() -> None:
    parsed = parse_args(sys.argv[1:])
    if parsed.get("list"):
        cmd_list()
        return

    count = parsed["count"]
    detect = parsed["detect"]
    sel = parsed["schemas"]

    chosen: list = []
    if "__all__" in sel:
        chosen = ALGEBRA_SCHEMAS
    elif sel:
        for a in sel:
            key = a.lower()
            if key in BY_ID:
                chosen.append(BY_ID[key])
            elif key in BY_NAME:
                chosen.append(BY_NAME[key])
            else:
                print(f"  ! unknown schema: {a}")
        if not chosen:
            print("  No valid schemas selected. Run `python train.py --list`.")
            return
    else:
        # no schema named: detection -> detection schemas, else all
        chosen = DETECT_SCHEMAS if detect else ALGEBRA_SCHEMAS

    CCTTrainer(chosen, num_problems=count, detect=detect).run()


if __name__ == "__main__":
    main()
