#!/usr/bin/env python3
"""
verify-fire-engine.py — End-to-end verification of the FIRe engine + mastery sync.

Checks all components: scan_vault, sync_exercise_mastery, compute_fire_scores,
build_diagnostic, apply_fire_to_srs (empty + real SRS state), report rendering,
and forced-mismatch recovery.

Exit code 0 = all pass. Prints summary per check.
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")


import sys, json, tempfile, re
from pathlib import Path

VAULT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VAULT))

import flow_diagnostic as md

def check(name, condition, detail=""):
    status = "✅" if condition else "❌"
    print(f"{status}  {name}  {detail}")
    if not condition:
        sys.exit(1)

# 1. scan_vault — exercises and implicit_review parsing
exs, topics = md.scan_vault()
check("scan_vault: finds exercises", len(exs) > 0, f"({len(exs)} total)")
irc = sum(1 for e in exs.values() if e.get("implicit_review"))
check("scan_vault: parses implicit_review", irc > 0, f"({irc} with ireview)")

# 2. sync_exercise_mastery — detects 0 mismatches on clean vault
changes = md.sync_exercise_mastery(exs)
check("sync: clean vault has 0 mismatches", len(changes) == 0)

# 3. sync_exercise_mastery — forced-mismatch recovery (frontmatter + body tag)
target = None
for num, e in exs.items():
    if e["pct"] >= 1.0 and e["mastery"] == "mastered" and e.get("implicit_review"):
        target = num
        break
if target:
    tp = Path(exs[target]["path"])
    orig = tp.read_text(encoding="utf-8")
    broken = re.sub(r'^(mastery:\s*)mastered', r'\1familiar', orig, count=1, flags=re.MULTILINE)
    broken = re.sub(r'^#mastered', '#familiar', broken, count=1, flags=re.MULTILINE)
    tp.write_text(broken, encoding="utf-8")
    exs2, _ = md.scan_vault()
    changes2 = md.sync_exercise_mastery(exs2)
    check("sync: forced mismatch detected (count=1)", len(changes2) == 1)
    if changes2:
        check("sync: restored familiar→mastered",
              changes2[0][1] == "familiar" and changes2[0][2] == "mastered")
    tp.write_text(orig, encoding="utf-8")
else:
    print("⏭️  sync forced-mismatch: no suitable mastered exercise (skipped)")

# 3b. sync_exercise_mastery — forced display-text mismatch only
target2 = None
for num, e in sorted(exs.items()):
    if e["pct"] >= 1.0 and e["mastery"] == "mastered":
        tp = Path(e["path"])
        body = tp.read_text(encoding="utf-8")
        if re.search(r'Mastery:\s*\*\*(\S+)\*\*', body):
            target2 = num
            break
if target2:
    tp = Path(exs[target2]["path"])
    orig = tp.read_text(encoding="utf-8")
    broken = re.sub(r'(Mastery:\s*\*\*)(\S+)(\*\*)', r'\1familiar\3', orig, count=1)
    tp.write_text(broken, encoding="utf-8")
    exs3, _ = md.scan_vault()
    changes3 = md.sync_exercise_mastery(exs3)
    check("sync: display-text-only mismatch detected", len(changes3) == 1, f"got {len(changes3)}")
    if changes3:
        check("sync: display-text restored to mastered", changes3[0][2] == "mastered")
    restored = tp.read_text(encoding="utf-8")
    dm = re.search(r'Mastery:\s*\*\*(\S+)\*\*', restored)
    check("sync: display-text verified on re-read",
          dm and dm.group(1).lower() == "mastered",
          f"got '{dm.group(1) if dm else 'no match'}'")
    tp.write_text(orig, encoding="utf-8")
else:
    print("⏭️  sync display-text: no mastered file with Mastery:** pattern (skipped)")

# 4. compute_fire_scores — returns valid data
by_num = {n: e for n, e in exs.items()}
fire = md.compute_fire_scores(exs, by_num)
check("fire_scores: returns data", len(fire) > 0, f"({len(fire)} scored)")
nz = sum(1 for f in fire.values() if f["total_weight"] > 0)
check("fire_scores: non-zero weights", nz > 0, f"({nz} with weight > 0)")

# 5. build_diagnostic includes fire_data
diag = md.build_diagnostic(exs, topics)
check("diagnostic: fire_data present", "fire_data" in diag)
check("diagnostic: fire_data non-empty", len(diag["fire_data"]) > 0)

# 6. apply_fire_to_srs with empty state
tmp = Path(tempfile.mkstemp(suffix=".json")[1])
try:
    tmp.write_text(json.dumps({"reviews": {}}), encoding="utf-8")
    changes = md.apply_fire_to_srs(exs, srs_path=tmp)
    check("apply_fire(empty): graceful", "No fractional" in " ".join(changes))
finally:
    try: tmp.unlink()
    except PermissionError: pass

# 7. apply_fire_to_srs with real state (if it exists)
real = VAULT / ".obsidian" / "srs_state.json"
if real.exists():
    changes = md.apply_fire_to_srs(exs, srs_path=real)
    check("apply_fire(real): no crash", len(changes) >= 1)
else:
    print("⏭️  apply_fire(real): no srs_state.json (skipped)")

# 8. Markdown report contains all required sections
report = md.render_markdown_report(diag)
check("markdown: FIRe section", "🔥 FIRe Multiplier" in report)
check("markdown: SRS section", "🔴 SRS Due Today" in report)
check("markdown: Flow Zone section", "🔥 Flow Zone" in report)
check("markdown: Topic Summary section", "📊 Topic Mastery Summary" in report)

# 9. Short report contains FIRe tags
short = md.render_short_report(diag)
check("short: FIRe indicators", "FIRe" in short)

# 10. Check a sample exercise with prerequisites: frontmatter matches implicit_review
sample = next((x for x in exs.values() if x.get("prerequisites")), None)
check("sample exercise with prereqs exists", sample is not None)
check("sample prereqs mirrored into implicit_review",
      not sample.get("implicit_review")
      or set(sample["prerequisites"]) >= set(sample["implicit_review"])
      or set(sample["implicit_review"]) >= set(sample["prerequisites"]))

# 11. fire_populate.py compiles
compile((VAULT / "fire_populate.py").read_text(encoding="utf-8"),
        "fire_populate.py", "exec")
check("fire_populate.py compiles", True)

# 12. Terminal report runs without error
import io
old_out = sys.stdout
sys.stdout = io.StringIO()
try:
    md.main()
    output = sys.stdout.getvalue()
    check("terminal report runs", "Flow Zone" in output)
finally:
    sys.stdout = old_out

print(f"\n{'='*50}")
print(f"PASS: All checks passed.")
