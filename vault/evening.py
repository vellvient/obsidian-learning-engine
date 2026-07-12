#!/usr/bin/env python3
"""
evening.py — single evening entrypoint for the math vault.

Runs:
  1. mastery sync + Flow Zone Diagnostic markdown
  2. FIRe chain boost
  3. Review Grader + SRS Tracker regen
  4. optional sprint status report

Usage:
  python evening.py
"""
from __future__ import annotations
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")
from pathlib import Path

VAULT = Path(__file__).resolve().parent


def run(cmd: list) -> int:
    print(f"\n$ {' '.join(cmd)}")
    return subprocess.call(cmd, cwd=str(VAULT))


def main():
    print("=" * 64)
    print("  EVENING — sync + diagnostic")
    print("=" * 64)

    run([sys.executable, "flow_diagnostic.py", "--markdown"])
    run([sys.executable, "flow_diagnostic.py", "--apply-fire"])
    run([sys.executable, "srs_fsrs.py", "--grader-note"])
    run([sys.executable, "srs_fsrs.py", "--tracker"])
    run([sys.executable, "scripts/sprint_status.py"])

    print("\nDone. Open 00 - Flow Zone Diagnostic.md for tomorrow's snapshot.")


if __name__ == "__main__":
    main()
