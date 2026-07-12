#!/usr/bin/env python3
"""
verify-batch-edges.py — Validate a prerequisite edge batch output JSON.

Usage:
    python verify-batch-edges.py <path/to/batch_edges.json> [options]

Options:
    --master-index <path>   Cross-reference all (from,to) IDs against master_index_compact.txt
    --batch <path>          Check for duplicating existing edges from the source batch JSON
    --verbose               Print all edges that pass

Checks (always):
  - Valid JSON syntax
  - All required fields present (from, to, type, reason)
  - Valid edge types (HARD_PREREQ, SOFT_PREREQ, IMPLICIT_REVIEW)
  - No duplicate (from, to) pairs
  - No self-loops (from == to)
  - No same-type transitivity violations (A->B and B->C implies A->C is redundant)
  - from/to are non-negative integers

With --master-index:
  - Every (from, to) ID exists as a valid exercise in the master index

With --batch:
  - No new edge duplicates an existing edge already recorded in the source batch
  - Checks existing_edges_in_batch, existing_prerequisites, AND existing_leads_to

Returns exit code 0 on pass, 1 on failure.
"""

import json, sys, argparse

VALID_TYPES = {'HARD_PREREQ', 'SOFT_PREREQ', 'IMPLICIT_REVIEW'}


def load_master_index(path):
    """Return set of all exercise numbers from master_index_compact.txt.

    Parsing pitfall: the file has a variable-width format.
        seq|counter|name|domain|slug          (lines 1-11, id==seq)
        seq|counter|id|name|domain|slug       (lines 12+, id >= 100)
    Use split() without limit and check field count to find the ID.
    """
    ids = set()
    bad_lines = []
    with open(path, encoding='utf-8') as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            parts = line.split('|')
            n = len(parts)
            val = None
            if n >= 6 and parts[2].strip().isdigit():
                val = int(parts[2])          # id column (lines 12+)
            elif n >= 5 and parts[1].strip().isdigit():
                val = int(parts[1])          # id == counter (lines 1-11)
            if val is not None:
                ids.add(val)
            else:
                bad_lines.append((lineno, line[:60]))
    if bad_lines:
        print(f"  WARN load_master_index: {len(bad_lines)} unparseable line(s):", file=sys.stderr)
        for lno, txt in bad_lines:
            print(f"    L{lno}: {txt}", file=sys.stderr)
    return ids


def load_existing_edges(path):
    """Return set of (from, to) pairs from batch JSON.

    Collects from THREE sources:
      1. existing_edges_in_batch[]
      2. each exercise's existing_prerequisites[]
      3. each exercise's existing_leads_to[]
    """
    with open(path, encoding='utf-8') as f:
        batch = json.load(f)
    existing = set()
    for e in batch.get('existing_edges_in_batch', []):
        existing.add((e['from'], e['to']))
    for ex in batch.get('exercises', []):
        num = ex.get('num')
        for p in ex.get('existing_prerequisites', []):
            existing.add((p, num))
        for t in ex.get('existing_leads_to', []):
            existing.add((num, t))
    return existing


def check_transitivity(edges, existing=None):
    """Detect same-type transitive chains A->B->C where A->C also exists.

    If `existing` is provided, also checks whether A->C is transitively
    covered by (A->B in proposed ∪ existing) and (B->C in proposed ∪ existing).
    Uses a conservative approach: any existing edge (any type) is considered
    a potential link in a transitive chain, since mixing a proposed edge with
    an existing edge of any type can create a transitive path.
    """
    pairs_by_type = {}
    for e in edges:
        pairs_by_type.setdefault(e['type'], set()).add((e['from'], e['to']))

    # Build the full graph: proposed edges + existing edges
    full_by_type = {}
    for t, s in pairs_by_type.items():
        full_by_type[t] = set(s)
    if existing:
        for (f, t) in existing:
            for typ in VALID_TYPES:
                full_by_type.setdefault(typ, set())
                full_by_type[typ].add((f, t))

    errors = []
    for t, full in full_by_type.items():
        for a, b in full:
            for c in [to for f2, to in full if f2 == b]:
                if (a, c) in pairs_by_type.get(t, set()):
                    # Only flag if A->C is in the PROPOSED set
                    for e in edges:
                        if e['from'] == a and e['to'] == c and e['type'] == t:
                            errors.append(
                                f"Transitivity ({t}): {a}->{b}->{c} AND proposed {a}->{c} "
                                f"both exist in (proposed ∪ existing) — remove {a}->{c} "
                                f"unless it is a distinct conceptual dependency")
                            break
    return errors


def main():
    parser = argparse.ArgumentParser(description='Validate prerequisite edge batch JSON.')
    parser.add_argument('path', help='Path to batch_edges.json')
    parser.add_argument('--master-index', help='Path to master_index_compact.txt for ID cross-referencing')
    parser.add_argument('--batch', help='Path to source batch JSON (checks existing edges)')
    parser.add_argument('--verbose', action='store_true', help='Print passing edges')
    args = parser.parse_args()

    # 1. Parse edges
    try:
        with open(args.path, encoding='utf-8') as f:
            edges = json.load(f)
    except Exception as e:
        print(f"FAIL: Could not parse JSON -- {e}")
        sys.exit(1)

    if not isinstance(edges, list):
        print(f"FAIL: Expected JSON array, got {type(edges).__name__}")
        sys.exit(1)

    print(f"Loaded {len(edges)} edges from {args.path}")

    # 2. Optionally load master index
    master_ids = None
    if args.master_index:
        master_ids = load_master_index(args.master_index)
        print(f"Master index: {len(master_ids)} exercises loaded from {args.master_index}")

    # 3. Optionally load existing batch edges (from all 3 sources)
    existing = set()
    if args.batch:
        existing = load_existing_edges(args.batch)
        print(f"Existing edges in batch (prereqs + leads_to + edges_in_batch): {len(existing)}")

    # 4. Validate each edge
    errors = []
    pairs = set()
    from_ids_seen = set()
    to_ids_seen = set()

    for i, e in enumerate(edges):
        # Required fields
        for field in ('from', 'to', 'type', 'reason'):
            if field not in e:
                errors.append(f"[{i}] Missing field: '{field}'")
                continue

        f_val, t_val, typ, rsn = e['from'], e['to'], e['type'], e['reason']

        # Type validity
        if typ not in VALID_TYPES:
            errors.append(f"[{i}] Invalid type '{typ}' -- expected one of {sorted(VALID_TYPES)}")

        # Reason quality
        if not isinstance(rsn, str) or len(rsn) < 10:
            errors.append(f"[{i}] 'reason' too short ({len(rsn) if isinstance(rsn, str) else 'not a string'} chars)")

        # Numeric sanity
        if not isinstance(f_val, int) or f_val < 0:
            errors.append(f"[{i}] 'from' must be non-negative int, got {type(f_val).__name__} {f_val}")
        if not isinstance(t_val, int) or t_val < 0:
            errors.append(f"[{i}] 'to' must be non-negative int, got {type(t_val).__name__} {t_val}")

        # Self-loop
        if isinstance(f_val, int) and isinstance(t_val, int) and f_val == t_val:
            errors.append(f"[{i}] Self-loop: {f_val} -> {f_val}")

        # Duplicate within proposed set
        p = (f_val, t_val)
        if p in pairs:
            errors.append(f"[{i}] Duplicate edge: {f_val} -> {t_val}")
        pairs.add(p)

        # Duplicates existing batch edges
        if p in existing:
            errors.append(f"[{i}] Duplicates existing edge in source batch: {f_val} -> {t_val}")

        # Track for stats
        if isinstance(f_val, int):
            from_ids_seen.add(f_val)
        if isinstance(t_val, int):
            to_ids_seen.add(t_val)

        # Master index cross-reference
        if master_ids is not None and isinstance(f_val, int) and isinstance(t_val, int):
            if f_val not in master_ids:
                errors.append(f"[{i}] 'from'={f_val} not found in master index")
            if t_val not in master_ids:
                errors.append(f"[{i}] 'to'={t_val} not found in master index")

    # 5. Transitivity check (against proposed ∪ existing)
    errors.extend(check_transitivity(edges, existing if existing else None))

    # 6. Report
    if errors:
        print(f"\nFAIL -- {len(errors)} issue(s):")
        for err in errors:
            print(f"  ! {err}")
        sys.exit(1)

    print(f"PASS -- {len(edges)} edges, no issues.")

    # Statistics
    types_used = {e['type'] for e in edges}
    print(f"  Types: {sorted(types_used)}")
    print(f"  From IDs: {min(from_ids_seen)}-{max(from_ids_seen)} ({len(from_ids_seen)} unique)")
    print(f"  To IDs:   {min(to_ids_seen)}-{max(to_ids_seen)} ({len(to_ids_seen)} unique)")

    # Cross-domain report
    if master_ids:
        cross_domain_from = {v for v in from_ids_seen if v not in to_ids_seen and v in master_ids}
        print(f"  Cross-domain 'from' IDs: {sorted(cross_domain_from) if cross_domain_from else 'none'}")

    if args.verbose:
        for e in edges:
            print(f"  OK  {e['from']:>4} -> {e['to']:<4}  ({e['type']:15s})  {e['reason'][:70]}...")

    if existing:
        new_edges = pairs - existing
        print(f"  New edges (not in existing batch edges): {len(new_edges)}")


if __name__ == '__main__':
    main()
