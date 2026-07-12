#!/usr/bin/env python3
"""
make_compact.py — Strip master_index from batch JSON files.

Creates compact_batch_*.json files (no embedded master_index, no hermes_config/manifest)
and a shared master_index_compact.txt reference file.

Usage:
    python scripts/make_compact.py --input-dir /path/to/batches
    python scripts/make_compact.py --input-dir .   # current dir
"""

import argparse
import json
import os
import sys
from pathlib import Path


def make_compact(input_dir: str) -> None:
    """Create compact batch files + shared master index."""
    d = Path(input_dir)
    if not d.is_dir():
        print(f"ERROR: {input_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    # Collect all batch_*.json files (skip compact_, hermes_, manifest)
    batch_files = sorted([
        f for f in os.listdir(d)
        if f.startswith("batch_") and f.endswith(".json")
        and not f.startswith("compact_")
    ])

    if not batch_files:
        print("ERROR: No batch_*.json files found", file=sys.stderr)
        sys.exit(1)

    # Extract master_index from the first batch (all batches have the same one)
    first = json.load(open(d / batch_files[0], encoding="utf-8"))
    master_index = first.get("master_index")
    if not master_index:
        print("ERROR: First batch file has no 'master_index' key", file=sys.stderr)
        sys.exit(1)

    # Write compact master index reference
    compact_lines = []
    for ex in master_index:
        compact_lines.append(f"{ex['num']}|{ex['name']}|{ex['domain']}|{ex['topic']}")
    (d / "master_index_compact.txt").write_text("\n".join(compact_lines), encoding="utf-8")
    print(f"Created master_index_compact.txt ({len(master_index)} exercises, {len(compact_lines)} lines)")

    total_orig = 0
    total_compact = 0

    for fname in batch_files:
        path = d / fname
        data = json.load(open(path, encoding="utf-8"))

        if not isinstance(data, dict):
            print(f"SKIP {fname}: not a dict (type={type(data).__name__})")
            continue

        # Build compact version
        compact = {}
        for k, v in data.items():
            if k != "master_index":
                compact[k] = v
        compact["master_index_ref"] = "See master_index_compact.txt for full cross-domain index"

        compact_path = d / ("compact_" + fname)
        json.dump(compact, open(compact_path, "w", encoding="utf-8"), indent=2)

        orig_kb = path.stat().st_size // 1024
        compact_kb = compact_path.stat().st_size // 1024
        total_orig += orig_kb
        total_compact += compact_kb
        print(f"  {fname}: {orig_kb}KB -> {compact_kb}KB")

    print(f"\nDone. {len(batch_files)} batch files processed ({total_orig}KB -> {total_compact}KB total)")


def main():
    parser = argparse.ArgumentParser(description="Strip master_index from batch JSON files")
    parser.add_argument("--input-dir", required=True, help="Directory containing batch_*.json files")
    args = parser.parse_args()
    make_compact(args.input_dir)


if __name__ == "__main__":
    main()
