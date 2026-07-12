#!/usr/bin/env python3
"""
unlock_priority.py - rank vault skills by how many OTHER skills they unlock.

Reads the prerequisite graph from exercise frontmatter + prereq-mining batch
edges, then ranks every not-done skill on three metrics:

  1. IN_DEGREE      # of not-done skills that list X as a DIRECT prerequisite.
                   X is a hub: mastering it feeds the most downstream steps.
  2. FULLY_UNBLOCKS # of not-done skills whose ONLY missing prereq is X.
                   Purest single-gate unlock power - they become startable now.
  3. DOWNSTREAM     total descendants of X (long-term leverage).

Also supports a decayed-aware mode (--decayed) implementing the user's
catch-up strategy: "learn NEW topics that reuse my decayed (due-for-review)
material, so one session reviews old stuff by learning new stuff."

GOTCHAS (see references/catchup-unlock-strategy.md):
  * Naive DOWNSTREAM subtree size collapses onto graph ROOTS
    ("numbers up to 100" gates ~500 skills only because it's the trunk).
    Exclude already-known primary roots; prefer IN_DEGREE / FULLY_UNBLOCKS.
  * Mastered hubs (199, 362, 193, 252, 267...) ALREADY PAID OFF - they still
    show high in-degree but their value is realized. The script flags them
    ([mastered]) so you don't re-prioritize already-banked hubs.
  * Missing prereq IDs (a prereq that has no note file, e.g. 638) must be
    skipped via `if p in ids`, never crash.

Usage (run from the vault root):
  python scripts/unlock_priority.py
  python scripts/unlock_priority.py --frontier          # A-Level IDs 130-720 only
  python scripts/unlock_priority.py --top 30
  python scripts/unlock_priority.py --decayed           # decayed-aware learn-new ranking
  python scripts/unlock_priority.py --decayed --as-of 2026-07-09
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

import os, re, glob, json, argparse
from collections import defaultdict, deque
from datetime import datetime

def find_vault(start):
    cur = os.path.abspath(start)
    for _ in range(6):
        if os.path.exists(os.path.join(cur, "flow_diagnostic.py")) or \
           any(re.match(r'^\d+\s*-', f) for f in os.listdir(cur) if f.endswith('.md')):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return os.getcwd()

def get_fm(fp, field):
    txt = open(fp, encoding='utf-8', errors='replace').read()
    if not txt.startswith('---'):
        return None
    m = re.search(rf'^{field}:\s*(.*)$', txt.split('---', 2)[1], re.M)
    return m.group(1).strip() if m else None

def parse_list(s):
    if not s or s.strip() == '[]':
        return []
    return [int(i) for i in re.findall(r'(\d+)', s)]

def load_graph(vault):
    ids, mastery, prereqs = {}, {}, defaultdict(list)
    for fp in glob.glob(os.path.join(vault, "*.md")):
        m = re.match(r'^(\d+)\s*-', os.path.basename(fp))
        if not m:
            continue
        eid = int(m.group(1))
        ids[eid] = os.path.basename(fp)[:-3]
        mastery[eid] = get_fm(fp, 'mastery') or 'not-started'
        prereqs[eid] = parse_list(get_fm(fp, 'prerequisites'))
    for bf in glob.glob(os.path.join(vault, ".engine", "prereq_mining", "results", "batch_*_result.json")):
        try:
            d = json.load(open(bf, encoding='utf-8', errors='replace'))
        except Exception:
            continue
        edges = d if isinstance(d, list) else (d.get('edges') or d.get('results') or [])
        for e in edges:
            if not isinstance(e, dict):
                continue
            sm = re.search(r'(\d+)', str(e.get('src') or e.get('source') or e.get('from') or ''))
            tm = re.search(r'(\d+)', str(e.get('tgt') or e.get('target') or e.get('to') or ''))
            if sm and tm:
                s, t = int(sm.group(1)), int(tm.group(1))
                if s not in prereqs[t]:
                    prereqs[t].append(s)
    return ids, mastery, prereqs

def children_of(prereqs):
    ch = defaultdict(list)
    for eid in prereqs:
        for p in prereqs[eid]:
            ch[p].append(eid)
    return ch

def downstream(start, children):
    seen = set(); q = deque([start])
    while q:
        n = q.popleft()
        for c in children.get(n, []):
            if c not in seen:
                seen.add(c); q.append(c)
    seen.discard(start)
    return seen

def load_decayed(vault, as_of):
    sp = os.path.join(vault, ".obsidian", "srs_state.json")
    if not os.path.exists(sp):
        return set()
    data = json.load(open(sp, encoding='utf-8', errors='replace'))
    reviews = data.get("reviews", {})
    def parse(dt):
        return datetime.strptime(dt[:19], "%Y-%m-%dT%H:%M:%S")
    out = set()
    for r in reviews.values():
        for s in r.get("review_stages", []):
            if "due" in s and parse(s["due"]) <= as_of:
                sm = re.match(r'(\d+)', r.get("skill", ""))
                if sm:
                    out.add(int(sm.group(1)))
    return out

def nm(ids, eid):
    s = ids.get(eid, '?')
    return s.split(' - ', 1)[1][:46] if ' - ' in s else s

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("vault", nargs="?", default=None)
    ap.add_argument("--frontier", action="store_true", help="restrict to A-Level IDs 130-720")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--decayed", action="store_true", help="decayed-aware learn-new ranking")
    ap.add_argument("--as-of", default="2026-07-09", help="YYYY-MM-DD for decayed calc")
    args = ap.parse_args()

    vault = args.vault or find_vault(os.getcwd())
    ids, mastery, prereqs = load_graph(vault)
    children = children_of(prereqs)
    done = lambda e: mastery.get(e) in ('mastered', 'proficient')

    def in_scope(eid):
        if done(eid):
            return False
        if args.frontier and not (130 <= eid <= 720):
            return False
        return True

    indeg = defaultdict(list)
    for eid in ids:
        if not in_scope(eid):
            continue
        for p in prereqs[eid]:
            if p in ids:
                indeg[p].append(eid)

    fully = defaultdict(list)
    for eid in ids:
        if done(eid):
            continue
        pr = prereqs[eid]
        if not pr:
            continue
        missing = [p for p in pr if not done(p)]
        if len(missing) == 1:
            fully[missing[0]].append(eid)

    print(f"Vault: {vault}  |  nodes={len(ids)}  |  frontier={args.frontier}")
    print("\n=== TOP HUBS by DIRECT in-degree (not-done skills that depend on X) ===")
    for x in sorted(indeg, key=lambda k: -len(indeg[k]))[:args.top]:
        if x not in ids:
            continue
        flag = "[mastered]" if mastery.get(x) in ('mastered', 'proficient') else ""
        print(f"{x:>4} [{mastery.get(x,'?'):<9}] depends-on={len(indeg[x]):>3} {flag} {nm(ids,x)}")

    print("\n=== TOP by FULLY-UNBLOCKS (single remaining gate -> immediately startable) ===")
    for x in sorted(fully, key=lambda k: -len(fully[k]))[:args.top]:
        if x not in ids:
            continue
        flag = "[mastered]" if mastery.get(x) in ('mastered', 'proficient') else ""
        print(f"{x:>4} [{mastery.get(x,'?'):<9}] unblocks={len(fully[x]):>3} {flag} {nm(ids,x)}")

    if args.decayed:
        as_of = datetime.strptime(args.as_of, "%Y-%m-%d")
        decayed = load_decayed(vault, as_of)
        print(f"\n=== DECAYED-AWARE: not-done topics that review the most decayed prereqs ({len(decayed)} overdue) ===")
        print("(learn these = review old material for free)\n")
        ranked = []
        for eid in ids:
            if done(eid):
                continue
            dec = [p for p in prereqs[eid] if p in decayed]
            if dec:
                ranked.append((eid, len(dec), sorted(dec)))
        ranked.sort(key=lambda x: -x[1])
        for eid, ndec, dec in ranked[:args.top]:
            print(f"{eid:>4} [{mastery.get(eid,'?'):<9}] reviews {ndec}: {nm(ids,eid)}  <- {dec}")

    print("\n(recompute anytime; mastered hubs flagged [mastered] = value already realized)")

if __name__ == "__main__":
    main()
