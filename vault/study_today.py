#!/usr/bin/env python3
"""
study_today.py — single "what should I study today" command.

Merges:
  1. FLOW ZONE — prereqs mastered, not finished
  2. FULLY_UNBLOCKS — sole-gate unlock leverage
  3. WEAK SPOTS — IDs from Weak Spots Priority + Error Log (boosted)
  4. MICRO-SCHEMA bridge suggestions for top picks

Usage (run from vault root):
  python study_today.py
  python study_today.py --top 15
  python study_today.py --frontier        # A-Level IDs 130-720 only
"""
import os, re, glob, json, argparse, sys
from collections import defaultdict

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

VAULT = os.path.dirname(os.path.abspath(__file__))


def load_graph(vault):
    ids, mastery, prereqs = {}, {}, defaultdict(list)
    for fp in glob.glob(os.path.join(vault, "*.md")):
        m = re.match(r'^(\d+)\s*-', os.path.basename(fp))
        if not m:
            continue
        eid = int(m.group(1))
        ids[eid] = os.path.basename(fp)[:-3]
        txt = open(fp, encoding="utf-8", errors="replace").read()
        fm = txt.split("---", 2)[1] if txt.startswith("---") else ""
        mv = re.search(r'^mastery:\s*(.*)$', fm, re.M)
        mastery[eid] = (mv.group(1).strip() if mv else "not-started") or "not-started"
        pv = re.search(r'^prerequisites:\s*(.*)$', fm, re.M)
        prereqs[eid] = [int(i) for i in re.findall(r'(\d+)', pv.group(1))] if pv else []
    for bf in glob.glob(os.path.join(vault, ".engine", "prereq_mining", "results", "batch_*_result.json")):
        try:
            d = json.load(open(bf, encoding="utf-8", errors="replace"))
        except Exception:
            continue
        edges = d if isinstance(d, list) else (d.get("edges") or d.get("results") or [])
        for e in edges:
            if not isinstance(e, dict):
                continue
            sm = re.search(r'(\d+)', str(e.get("src") or e.get("source") or e.get("from") or ""))
            tm = re.search(r'(\d+)', str(e.get("tgt") or e.get("target") or e.get("to") or ""))
            if sm and tm:
                s, t = int(sm.group(1)), int(tm.group(1))
                if s not in prereqs[t]:
                    prereqs[t].append(s)
    return ids, mastery, prereqs


def nm(ids, eid):
    s = ids.get(eid, str(eid))
    return s[:50]


def fully_unblocks(ids, mastery, prereqs):
    fully = defaultdict(list)
    done = lambda e: mastery.get(e) in ("mastered", "proficient")
    for eid in ids:
        if done(eid):
            continue
        pr = prereqs[eid]
        if not pr:
            continue
        missing = [p for p in pr if not done(p)]
        if len(missing) == 1:
            fully[missing[0]].append(eid)
    return fully


def weak_spot_ids(vault):
    ids = []
    for name in ("00 - Weak Spots Priority.md", "00 - Error Log.md"):
        path = os.path.join(vault, name)
        if not os.path.exists(path):
            continue
        text = open(path, encoding="utf-8", errors="replace").read()
        for m in re.finditer(r"\[\[(\d+)\s*-", text):
            ids.append(int(m.group(1)))
        for m in re.finditer(r"(?:#|exercise\s+)(\d{2,4})\b", text, re.I):
            ids.append(int(m.group(1)))
    seen, out = set(), []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--frontier", action="store_true", help="A-Level IDs 130-720 only")
    args = ap.parse_args()

    import flow_diagnostic as diag
    exercises, _ = diag.scan_vault()
    built = diag.build_diagnostic(exercises, {})
    flow = built.get("flow_zone", [])
    flow_nums = {int(t[0]) for t in flow}
    srs = built.get("srs_due", [])
    leg = built.get("legacy_srs_meta", {})

    ids, mastery, prereqs = load_graph(VAULT)
    fully = fully_unblocks(ids, mastery, prereqs)
    weak = set(weak_spot_ids(VAULT))

    def practice_note(n):
        return os.path.join(VAULT, "practice", f"{n} - Practice.md")

    def in_prog(n):
        ex = exercises.get(n, {})
        done, total = ex.get("progress", (0, 0))
        return 0 < done < total

    ranked = []
    for n in flow_nums:
        if args.frontier and not (130 <= n <= 720):
            continue
        leverage = len(fully.get(n, []))
        prog_bonus = 1 if in_prog(n) else 0
        weak_bonus = 2 if n in weak else 0
        ranked.append((n, leverage, prog_bonus, weak_bonus, mastery.get(n, "?")))

    # most leverage, then weak-spot boost, then in-progress
    ranked.sort(key=lambda x: (-x[1], -x[3], -x[2], x[4]))

    print(f"=== STUDY TODAY ({len(ranked)} flow-zone items, ranked by unlock leverage) ===\n")
    print(f"SRS due (FSRS compressed): {len(srs)}  |  legacy stages overdue: "
          f"{leg.get('overdue_stage_entries', '?')} / {leg.get('unique_skills', '?')} skills")
    print(f"{'#':>4}  {'leverage':>8}  {'status':<11}  exercise")
    print("-" * 70)
    for n, lev, prog, wk, mst in ranked[:args.top]:
        mark = "*" if prog else " "
        wmark = "!" if wk else " "
        pmark = "p" if os.path.exists(practice_note(n)) else " "
        print(f"{n:>4}{mark}{wmark}{pmark}{lev:>6}  {mst:<11} {nm(ids, n)}")
    print("\n* = in progress (closest win).  ! = weak-spot note boost.  "
          "p = practice note.  leverage = sole-gate unlocks.")

    # Micro-schema bridge for top 5
    try:
        from micro_bridge import suggest_for_ids
        pairs = [(n, nm(ids, n)) for n, *_ in ranked[:8]]
        sugg = suggest_for_ids(pairs)
        if sugg:
            print("\n=== MICRO-SCHEMA FLUENCY (after learning) ===")
            for s in sugg[:5]:
                print(f"  #{s['id']}: {', '.join(s['schemas'])}")
                print(f"       {s['cmd']}")
    except Exception as e:
        print(f"\n(micro_bridge skipped: {e})")

    # Topical past-paper practice for top picks (generated by gen_practice.py)
    withp = [n for n, *_ in ranked[:args.top] if os.path.exists(practice_note(n))]
    if withp:
        print("\n=== PAST-PAPER PRACTICE (topical) ===")
        for n in withp[:8]:
            try:
                head = open(practice_note(n), encoding="utf-8", errors="replace").read(600)
                m = re.search(r"\*\*(\d+) tagged", head)
                cnt = m.group(1) if m else "?"
            except OSError:
                cnt = "?"
            print(f"  #{n}: {cnt} questions  ->  practice/{n} - Practice.md")

    print("\nOrder: Review Grader (20–30) → finish * items → top 2 rows → CCT 5–10m.")
    print("Morning wrapper: python morning.py")


if __name__ == "__main__":
    main()
