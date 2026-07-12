#!/usr/bin/env python3
"""
log_error.py — one-command error capture for the math vault.

Replaces the screenshot -> Google Docs -> AI workflow with a single command
run the moment you get something wrong. Capture is instant (~5s); the deep
AI analysis happens later in batch via the /error-triage skill in Claude Code.

Usage (from vault root):
  python log_error.py 339 "forgot to flip inequality when dividing by negative"
  python log_error.py 339f "same" --again      # also FSRS-grade subskill 339f as Again
  python log_error.py "UKMT Senior Q17" "no idea how to start"   # non-vault problem
  python log_error.py 339f "sign slip" --shot  # attach the most recent screenshot

Flags:
  --shot     copy the newest screenshot (taken in the last 15 min) from
             Pictures/Screenshots into attachments/errors/ and embed it
  --again    if a subskill id (e.g. 339f) was given, grade that FSRS review
             as Again so the miss immediately affects scheduling
  --sev X    severity: slip | procedural | conceptual (default: unrated)

Entries land in "00 - Error Log.md" under "## 📝 Logged Errors",
newest first, tagged #unanalyzed for the batch triage pass.
"""
from __future__ import annotations
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

# console may be a non-UTF8 codepage (e.g. cp932); never crash on a print
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

VAULT = Path(__file__).resolve().parent
LOG_NOTE = VAULT / "00 - Error Log.md"
ATTACH_DIR = VAULT / "attachments" / "errors"

SCREENSHOT_DIRS = [
    Path.home() / "Pictures" / "Screenshots",
    Path.home() / "OneDrive" / "Pictures" / "Screenshots",
    Path.home() / "Pictures",
]
SCREENSHOT_MAX_AGE_MIN = 15


def resolve_exercise(ref: str):
    """'339' or '339f' -> (note_stem, subskill_id or None). Free text -> (ref, None)."""
    m = re.fullmatch(r"(\d+)([a-z]?)", ref.strip())
    if not m:
        return ref.strip(), None
    num, letter = m.group(1), m.group(2)
    hits = sorted(VAULT.glob(f"{num} - *.md"))
    if not hits:
        return ref.strip(), (num + letter if letter else None)
    return hits[0].stem, (num + letter if letter else None)


def grab_screenshot() -> Path | None:
    """Newest screenshot taken in the last SCREENSHOT_MAX_AGE_MIN minutes."""
    now = datetime.now().timestamp()
    best, best_mtime = None, 0.0
    for d in SCREENSHOT_DIRS:
        if not d.is_dir():
            continue
        for f in d.iterdir():
            if f.suffix.lower() not in (".png", ".jpg", ".jpeg"):
                continue
            mt = f.stat().st_mtime
            if now - mt <= SCREENSHOT_MAX_AGE_MIN * 60 and mt > best_mtime:
                best, best_mtime = f, mt
    if best is None:
        return None
    ATTACH_DIR.mkdir(parents=True, exist_ok=True)
    dest = ATTACH_DIR / f"{datetime.now():%Y-%m-%d_%H%M%S}{best.suffix.lower()}"
    shutil.copy2(best, dest)
    return dest


def grade_again(note_stem: str, subskill_id: str) -> str:
    """Best-effort FSRS Again grade for the subskill; returns a status line."""
    try:
        sys.path.insert(0, str(VAULT))
        from srs_fsrs import VaultFSRS, Rating
        v = VaultFSRS()
        prefix = f"{note_stem}.md:{subskill_id}:"
        keys = [k for k in v.state.get("reviews", {}) if k.startswith(prefix)]
        if not keys:
            return f"FSRS: no review found for {subskill_id} (not ticked yet?) — skipped"
        res = v.grade_review(keys[0], Rating.Again)
        v.save()
        return f"FSRS: {subskill_id} graded Again, next due {res['due'].date()}"
    except Exception as e:
        return f"FSRS: grade failed ({e})"


def build_entry(note_stem, subskill_id, desc, sev, shot: Path | None) -> str:
    ts = datetime.now()
    if (VAULT / f"{note_stem}.md").exists():
        where = f"[[{note_stem}]]" + (f" ({subskill_id})" if subskill_id else "")
    else:
        where = note_stem  # free-text context (UKMT, textbook, etc.)
    lines = [
        f"### {ts:%Y-%m-%d %H:%M} — {where} #unanalyzed",
        "",
        f"- **What happened:** {desc}",
        f"- **Severity (self-rated):** {sev}",
    ]
    if shot is not None:
        lines.append(f"- **Screenshot:** ![[{shot.relative_to(VAULT).as_posix()}]]")
    lines += [
        "- **Error type:** _pending triage_",
        "- **Root cause:** _pending triage_",
        "- **Fix / rule to remember:** _pending triage_",
        "- **Prerequisite gap:** _pending triage_",
        "",
    ]
    return "\n".join(lines)


def append_entry(entry: str):
    text = LOG_NOTE.read_text(encoding="utf-8", errors="replace")
    anchor = "## 📝 Logged Errors"
    if anchor in text:
        i = text.index(anchor) + len(anchor)
        text = text[:i] + "\n\n" + entry + "\n" + text[i:].lstrip("\n")
    else:
        text = text.rstrip() + "\n\n" + anchor + "\n\n" + entry + "\n"
    LOG_NOTE.write_text(text, encoding="utf-8")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    if len(args) < 2:
        print(__doc__)
        sys.exit(1)
    sev = "unrated"
    if "--sev" in sys.argv:
        try:
            sev = sys.argv[sys.argv.index("--sev") + 1]
            args = [a for a in args if a != sev]
        except IndexError:
            pass
    ref, desc = args[0], " ".join(args[1:])

    note_stem, subskill_id = resolve_exercise(ref)
    shot = grab_screenshot() if "--shot" in flags else None
    if "--shot" in flags and shot is None:
        print(f"(no screenshot found in the last {SCREENSHOT_MAX_AGE_MIN} min — logged without one)")

    append_entry(build_entry(note_stem, subskill_id, desc, sev, shot))
    print(f"Logged: {note_stem}" + (f" [{subskill_id}]" if subskill_id else ""))
    if shot:
        print(f"Screenshot attached: {shot.name}")

    if "--again" in flags and subskill_id and re.search(r"[a-z]$", subskill_id):
        print(grade_again(note_stem, subskill_id))
    n = LOG_NOTE.read_text(encoding="utf-8", errors="replace").count("#unanalyzed")
    print(f"{n} error(s) awaiting triage - run /error-triage in Claude Code to batch-analyse.")


if __name__ == "__main__":
    main()
