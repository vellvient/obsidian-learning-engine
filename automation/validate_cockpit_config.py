#!/usr/bin/env python3
"""Validate a subject cockpit configuration without reading personal state."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


def read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return default


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault", type=Path, required=True)
    args = parser.parse_args()
    vault = args.vault.resolve()
    catalog = read(vault / "config" / "course_catalog.json", {})
    errors = []
    if not catalog.get("profiles"):
        errors.append("no course profiles")
    error_rows = catalog.get("assessment", {}).get("error_types", [])
    error_ids = [str(row.get("id", "")) for row in error_rows if isinstance(row, dict)]
    if len(error_ids) != len(set(error_ids)) or any(not key for key in error_ids):
        errors.append("error type ids must be non-empty and unique")
    rubrics = catalog.get("assessment", {}).get("rubrics", [])
    for rubric in rubrics:
        dims = rubric.get("dimensions", [])
        ids = [str(row.get("id", "")) for row in dims]
        if not dims or len(ids) != len(set(ids)) or any(float(row.get("max", 0)) <= 0 for row in dims):
            errors.append(f"invalid rubric dimensions: {rubric.get('id', '?')}")
    curriculum = read(vault / ".engine" / "curriculum.json", [])
    curriculum_ids = {int(row.get("num", row.get("id"))) for row in curriculum}
    if not curriculum_ids:
        curriculum_ids = {
            int(match.group(1)) for path in vault.glob("*.md")
            if (match := re.match(r"^(\d+)\s+-\s+", path.name))
        }
    banks = []
    default_bank = ("papers/question_bank.json" if (vault / "papers/question_bank.json").exists()
                    else "papers/demo_question_bank.json")
    for item in catalog.get("question_banks", [{"path": default_bank}]):
        spec = {"path": item} if isinstance(item, str) else item
        rows = read(vault / spec["path"], [])
        if isinstance(rows, dict):
            rows = rows.get("questions") or rows.get("entries") or []
        banks.extend(rows)
    dangling = sorted({int(node) for row in banks for node in row.get("topic_node_ids", [])} - curriculum_ids)
    if dangling:
        errors.append(f"question tags reference {len(dangling)} unknown nodes")
    rubric_matches = Counter()
    for row in banks:
        component_type = str(row.get("component_type", "")).lower()
        component = str(row.get("component", ""))
        tags = {str(x).lower() for x in row.get("assessment_tags", [])}
        for rubric in rubrics:
            if (any(str(x).lower() in component_type for x in rubric.get("component_types", []))
                    or component[:1] in {str(x) for x in rubric.get("component_prefixes", [])}
                    or bool(tags & {str(x).lower() for x in rubric.get("assessment_tags", [])})):
                rubric_matches[rubric.get("id", "rubric")] += 1
                break
    for rubric in rubrics:
        if not rubric_matches[rubric.get("id", "rubric")]:
            errors.append(f"rubric matches no questions: {rubric.get('id', '?')}")
    report = {
        "vault": str(vault), "profiles": len(catalog.get("profiles", {})),
        "curriculum_nodes": len(curriculum_ids), "questions": len(banks),
        "error_types": len(error_ids), "rubric_matches": dict(rubric_matches),
        "errors": errors, "ok": not errors,
    }
    print(json.dumps(report, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
