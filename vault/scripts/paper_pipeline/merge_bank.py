#!/usr/bin/env python3
"""
merge_bank.py — merge Hermes paper-mining results into papers/question_bank.json.

Reads .engine/paper_mining/results/batch_*_result.json, dedupes by entry id,
validates each entry, and reports quality stats. Safe to run repeatedly
(idempotent; the bank is rebuilt from all result files each time).

Validation per entry:
  - has question text and at least one final answer
  - final_answers not "UNCLEAR" (counted separately, kept but flagged)
  - topic_node_ids reference exercise notes that actually exist in the vault

Usage (from vault root):
  python scripts/paper_pipeline/merge_bank.py
"""
from __future__ import annotations
import glob
import json
import re
import sys
from collections import Counter
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

VAULT = Path(__file__).resolve().parents[2]
RESULTS = VAULT / ".engine" / "paper_mining" / "results"
BANK = VAULT / "papers" / "question_bank.json"


def vault_note_ids() -> set:
    ids = set()
    for fp in VAULT.glob("*.md"):
        m = re.match(r"^(\d+)\s*-", fp.name)
        if m:
            ids.add(int(m.group(1)))
    return ids


def load_results():
    entries = {}
    for rf in sorted(RESULTS.glob("batch_*_result.json")):
        try:
            data = json.loads(rf.read_text(encoding="utf-8", errors="replace"))
        except Exception as e:
            print(f"SKIP {rf.name}: invalid JSON ({e})")
            continue
        items = data if isinstance(data, list) else data.get("entries", [])
        for e in items:
            if isinstance(e, dict) and e.get("id"):
                canonical_id(e)
                entries[e["id"]] = e  # later batches win on duplicate ids
    return entries


SESS_CODE = {"May/June": "s", "Oct/Nov": "w", "Feb/March": "m"}


def canonical_id(e: dict):
    """Rebuild id deterministically from fields (models sometimes mangle it)."""
    sc = SESS_CODE.get(str(e.get("session", "")).strip())
    if not sc:
        return  # keep model-provided id if session unrecognized
    try:
        yy = int(e["year"]) % 100
        e["id"] = f"{e['code']}_{sc}{yy:02d}_qp_{e['component']}_q{int(e['qnum'])}"
    except (KeyError, TypeError, ValueError):
        pass  # keep model-provided id if fields incomplete


def main():
    known = vault_note_ids()
    entries = load_results()
    if not entries:
        print("No results found in", RESULTS)
        return

    problems = Counter()
    for e in entries.values():
        if not (e.get("question") or "").strip():
            problems["missing_question"] += 1
        fa = e.get("final_answers") or []
        if not fa:
            problems["missing_answer"] += 1
        elif any("UNCLEAR" in str(a) for a in fa):
            problems["unclear_answer"] += 1
        tags = e.get("topic_node_ids") or []
        if not tags:
            problems["untagged"] += 1
        else:
            bad = [t for t in tags if t not in known]
            if bad:
                problems["bad_tag_ids"] += 1
                e["topic_node_ids"] = [t for t in tags if t in known]

    bank = sorted(entries.values(),
                  key=lambda e: (str(e.get("code")), -int(e.get("year") or 0),
                                 str(e.get("component")), int(e.get("qnum") or 0)))
    BANK.parent.mkdir(parents=True, exist_ok=True)
    BANK.write_text(json.dumps(bank, ensure_ascii=False, indent=1), encoding="utf-8")

    by_code = Counter(str(e.get("code")) for e in bank)
    by_diff = Counter(str(e.get("difficulty")) for e in bank)
    tag_cov = sum(1 for e in bank if e.get("topic_node_ids"))
    print(f"question_bank.json: {len(bank)} entries "
          f"({dict(by_code)}, difficulty {dict(by_diff)})")
    print(f"topic-tag coverage: {tag_cov}/{len(bank)} "
          f"({100 * tag_cov / len(bank):.0f}%)")
    if problems:
        print("issues:", dict(problems))
        print("(entries kept; fix prompts and re-run affected batches if rates are high)")
    # per-node question counts -> lets study tools serve questions by graph node
    node_counts = Counter()
    for e in bank:
        for t in e.get("topic_node_ids") or []:
            node_counts[t] += 1
    top = node_counts.most_common(8)
    if top:
        print("most-covered nodes:", ", ".join(f"#{n}({c})" for n, c in top))


if __name__ == "__main__":
    main()
