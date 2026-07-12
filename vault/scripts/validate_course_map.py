#!/usr/bin/env python3
"""Validate a course-overlay mapping before importing any notes or questions."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def note_ids(vault: Path) -> set[int]:
    out = set()
    for path in vault.glob("*.md"):
        match = re.match(r"^(\d+) - .+\.md$", path.name)
        if match:
            out.add(int(match.group(1)))
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mapping", type=Path)
    parser.add_argument("--vault", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--source-ids", type=Path,
                        help="optional JSON array of every source objective id")
    args = parser.parse_args()

    config = json.loads(args.mapping.read_text(encoding="utf-8"))
    mappings = {str(k): [int(x) for x in v] for k, v in config["mappings"].items()}
    new_nodes = {str(k): int(v) for k, v in config.get("new_nodes", {}).items()}
    existing = note_ids(args.vault)
    allowed = existing | set(new_nodes.values())

    errors = []
    empty = sorted(k for k, values in mappings.items() if not values)
    if empty:
        errors.append(f"objectives with no canonical targets: {empty}")
    dangling = sorted({x for values in mappings.values() for x in values} - allowed)
    if dangling:
        errors.append(f"canonical ids that neither exist nor are declared new: {dangling}")
    if len(set(new_nodes.values())) != len(new_nodes):
        errors.append("new_nodes contains duplicate canonical ids")
    collisions = sorted(set(new_nodes.values()) & existing)
    if collisions:
        errors.append(f"new node ids collide with existing notes: {collisions}")
    for source_id, new_id in new_nodes.items():
        if mappings.get(source_id) != [new_id]:
            errors.append(f"new objective {source_id} must map only to {new_id}")
    if args.source_ids:
        source_ids = {str(x) for x in json.loads(args.source_ids.read_text(encoding="utf-8"))}
        missing = sorted(source_ids - set(mappings))
        extra = sorted(set(mappings) - source_ids)
        if missing or extra:
            errors.append(f"coverage mismatch: missing={missing}, extra={extra}")

    if errors:
        for error in errors:
            print("FAIL:", error)
        raise SystemExit(1)
    targets = {x for values in mappings.values() for x in values}
    print(f"PASS: {len(mappings)} objectives -> {len(targets)} canonical nodes "
          f"({len(new_nodes)} new, {len(existing)} existing notes scanned)")


if __name__ == "__main__":
    main()
