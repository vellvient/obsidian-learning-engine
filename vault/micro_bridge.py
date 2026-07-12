#!/usr/bin/env python3
"""
micro_bridge.py — map vault exercise IDs → CCT micro-schema drills.

When a Flow Zone / in-progress exercise is recommended, suggest the matching
automaticity drill so understanding (vault) and fluency (CCT) stay linked.

Usage:
  python micro_bridge.py                 # print suggestions for flow-zone today
  python micro_bridge.py --for 387 413   # suggestions for specific IDs
  python micro_bridge.py --list          # dump full mapping
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

from __future__ import annotations
import re
import sys
from pathlib import Path

VAULT = Path(__file__).resolve().parent

# exercise id (or range keyword) → list of micro-schema ids
# Keep this table small and high-signal; expand as schemas grow.
EXERCISE_TO_SCHEMAS = {
    # Factorising / quadratics
    252: ["distributive"],
    253: ["distributive"],
    299: ["distributive", "perfect_square"],
    300: ["distributive"],
    362: ["diff_squares", "perfect_square"],
    363: ["diff_squares"],
    364: ["diff_squares", "perfect_square"],  # factor_pair external
    365: ["diff_squares", "perfect_square", "factor_grouping"],
    367: ["diff_squares", "perfect_square"],
    413: ["complete_square", "perfect_square"],
    414: ["complete_square"],
    415: ["complete_square"],
    416: ["complete_square"],
    417: ["discriminant"],
    492: ["discriminant"],
    # Indices / surds
    158: ["exponent_rules"],
    194: ["exponent_rules"],
    298: ["exponent_rules"],
    334: ["conjugate"],
    335: ["conjugate"],
    336: ["conjugate"],
    337: ["conjugate", "distributive"],
    392: ["conjugate"],
    393: ["conjugate"],
    394: ["exponent_rules"],
    395: ["exponent_rules", "conjugate"],
    # Algebraic fractions
    387: ["diff_squares", "distributive"],
    388: ["distributive"],
    389: ["distributive"],
    390: ["factor_grouping", "diff_squares"],
    # Logs / exp
    527: ["log_exp"],
    528: ["log_exp", "exponent_rules"],
    529: ["log_exp"],
    # Abs / modulus
    570: ["abs_value"],
    571: ["abs_value"],
    572: ["abs_value"],
    # Sum of cubes etc
    498: ["sum_cubes", "factor_grouping"],
    500: ["sum_cubes", "factor_grouping"],
}

# Topic name fragments → schemas (fallback when ID not mapped)
TOPIC_HINTS = [
    (r"factoris|quadratic", ["diff_squares", "perfect_square", "complete_square"]),
    (r"expand|bracket", ["distributive"]),
    (r"surd|rationalis", ["conjugate"]),
    (r"ind(ex|ices)|power", ["exponent_rules"]),
    (r"log|exponential", ["log_exp"]),
    (r"modulus|absolute", ["abs_value"]),
    (r"algebraic fraction", ["diff_squares", "distributive"]),
]


def schemas_for(exercise_id: int, name: str = "") -> list:
    if exercise_id in EXERCISE_TO_SCHEMAS:
        return list(EXERCISE_TO_SCHEMAS[exercise_id])
    low = (name or "").lower()
    for pat, schemas in TOPIC_HINTS:
        if re.search(pat, low):
            return list(schemas)
    return []


def suggest_for_ids(ids_with_names: list) -> list:
    """ids_with_names: [(id, name), ...] → [{id, name, schemas, cmd}, ...]"""
    out = []
    seen = set()
    for eid, name in ids_with_names:
        schemas = schemas_for(eid, name)
        if not schemas:
            continue
        key = (eid, tuple(schemas))
        if key in seen:
            continue
        seen.add(key)
        cmd = "python micro_trainer/train.py " + " ".join(schemas) + " --count 20"
        out.append({"id": eid, "name": name, "schemas": schemas, "cmd": cmd})
    return out


def main():
    args = sys.argv[1:]
    if "--list" in args:
        for eid in sorted(EXERCISE_TO_SCHEMAS):
            print(f"  {eid:>4}: {', '.join(EXERCISE_TO_SCHEMAS[eid])}")
        return
    if "--for" in args:
        i = args.index("--for")
        ids = []
        for a in args[i + 1 :]:
            if a.startswith("--"):
                break
            try:
                ids.append(int(a))
            except ValueError:
                pass
        pairs = [(n, "") for n in ids]
        for s in suggest_for_ids(pairs):
            print(f"#{s['id']}: {s['schemas']} → {s['cmd']}")
        return

    # Default: pull flow zone from diagnostic
    sys.path.insert(0, str(VAULT))
    import flow_diagnostic as diag

    exercises, _ = diag.scan_vault()
    built = diag.build_diagnostic(exercises, {})
    flow = built.get("flow_zone", [])
    stalled = built.get("stalled", [])
    pairs = []
    for item in list(flow)[:15] + list(stalled)[:10]:
        # flow items are (num, ex, status)
        if isinstance(item, tuple) and len(item) >= 2:
            num, ex = item[0], item[1]
            pairs.append((int(num), ex.get("name", "")))
    suggestions = suggest_for_ids(pairs)
    print("=== MICRO-SCHEMA BRIDGE (fluency drills for today's graph work) ===\n")
    if not suggestions:
        print("  (no mapped drills for current flow-zone items)")
        return
    for s in suggestions:
        print(f"  #{s['id']:<4} {s['name'][:40]:<40} → {', '.join(s['schemas'])}")
        print(f"         {s['cmd']}")
    print("\nRun a 5–10 min CCT block after new learning for automaticity.")


if __name__ == "__main__":
    main()
