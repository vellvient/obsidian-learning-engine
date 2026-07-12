#!/usr/bin/env python3
"""process_batches.py — drive DeepSeek V4 Flash over the paper-mining batches.

For every pending batch in .engine/paper_mining/manifest.json, invokes an
agent CLI that reads system_prompt.txt + the batch JSON and writes
results/{batch}_result.json. The driver validates the result (JSON array,
ids match the batch's papers), retries once on failure, updates the manifest,
and runs merge_bank.py after every 5 completed batches.

Engines:
  hermes   (default) `hermes -z` -> the reference setup's agent CLI (DeepSeek-class model)
  opencode `opencode run` -> free-tier fallback (slow queue)
  Any other agent CLI works: edit run_batch() - the contract is just
  "read the prompt, write the result file" (see README.md in this directory).

Usage (from vault root):
  python scripts/paper_pipeline/process_batches.py --limit 5     # one wave
  python scripts/paper_pipeline/process_batches.py               # all pending
  python scripts/paper_pipeline/process_batches.py --workers 4   # parallel agents
  python scripts/paper_pipeline/process_batches.py --engine opencode

Batches are independent (own batch file, own result file), so --workers N
runs N agent processes concurrently; the manifest and merges are serialized
behind a lock in this driver.
"""
from __future__ import annotations
import argparse
import json
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

VAULT = Path(__file__).resolve().parents[2]
MINING = VAULT / ".engine" / "paper_mining"
RESULTS = MINING / "results"
MANIFEST = MINING / "manifest.json"
MODEL = "opencode/deepseek-v4-flash-free"
BATCH_TIMEOUT = 1200  # seconds per opencode call

PROMPT = (
    "You are running a batch job. Steps, in order:\n"
    "1. Read the file .engine/paper_mining/system_prompt.txt - those are your "
    "content instructions.\n"
    "2. Read the file .engine/paper_mining/{batch_id}.json - the batch data "
    "(topic_index + papers with questions).\n"
    "3. Apply the system prompt rules to EVERY question of EVERY paper in the "
    "batch, especially rule 1 (id = paper_id + '_q' + qnum, exactly), rule 4 "
    "(final_answers from A1/B1 result lines) and rule 6 (topic_node_ids only "
    "from the embedded topic_index).\n"
    "4. Write the complete result to .engine/paper_mining/results/"
    "{batch_id}_result.json - the file content must be ONLY the JSON array of "
    "question-bank entries, nothing else.\n"
    "Do not modify any other file. Do not skip questions."
)


def load_manifest() -> list[dict]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def save_manifest(m: list[dict]):
    MANIFEST.write_text(json.dumps(m, indent=2), encoding="utf-8")


def expected_ids(batch_id: str) -> set[str]:
    data = json.loads((MINING / f"{batch_id}.json").read_text(encoding="utf-8"))
    return {f"{p['paper_id']}_q{q['qnum']}" for p in data["papers"]
            for q in p["questions"]}


def validate(batch_id: str) -> tuple[bool, str]:
    rf = RESULTS / f"{batch_id}_result.json"
    if not rf.exists():
        return False, "result file not written"
    try:
        data = json.loads(rf.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:
        return False, f"invalid JSON: {e}"
    if isinstance(data, dict):
        data = data.get("entries", [])
    if not isinstance(data, list) or not data:
        return False, "empty or non-array result"
    exp = expected_ids(batch_id)
    got = {e.get("id") for e in data if isinstance(e, dict)}
    matched = len(got & exp)
    if matched < max(1, int(0.6 * len(exp))):
        return False, f"only {matched}/{len(exp)} question ids matched"
    return True, f"{len(data)} entries ({matched}/{len(exp)} ids matched)"


def run_batch(batch_id: str, engine: str) -> bool:
    exe = shutil.which(engine)
    if not exe:
        sys.exit(f"{engine} CLI not found on PATH")
    prompt = PROMPT.replace("{batch_id}", batch_id)
    if engine == "hermes":
        cmd = [exe, "-z", prompt]
    else:
        cmd = [exe, "run", "-m", MODEL, "--title", f"paper-mining {batch_id}", prompt]
    for attempt in (1, 2):
        t0 = time.time()
        try:
            subprocess.run(cmd, cwd=VAULT, timeout=BATCH_TIMEOUT,
                           capture_output=True)
        except subprocess.TimeoutExpired:
            print(f"  {batch_id}: attempt {attempt} timed out after {BATCH_TIMEOUT}s")
            continue
        ok, msg = validate(batch_id)
        print(f"  {batch_id}: attempt {attempt} [{time.time() - t0:.0f}s] -> "
              f"{'OK' if ok else 'FAIL'}: {msg}")
        if ok:
            return True
        (RESULTS / f"{batch_id}_result.json").unlink(missing_ok=True)
    return False


def merge():
    subprocess.run([sys.executable, str(VAULT / "scripts" / "paper_pipeline" / "merge_bank.py")],
                   cwd=VAULT)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="max batches this run (0 = all)")
    ap.add_argument("--engine", choices=["hermes", "opencode"], default="hermes")
    ap.add_argument("--workers", type=int, default=1, help="concurrent agent processes")
    args = ap.parse_args()

    manifest = load_manifest()
    todo = [i for i in manifest if i["status"] != "completed"]
    if args.limit:
        todo = todo[:args.limit]

    lock = threading.Lock()
    state = {"done": 0, "failed": 0, "since_merge": 0, "stop": False}

    def job(item):
        bid = item["batch_id"]
        ok, msg = validate(bid)   # pre-existing valid result? just mark it
        if ok:
            print(f"  {bid}: existing result valid -> {msg}")
        else:
            if state["stop"]:
                return
            ok = run_batch(bid, args.engine)
        with lock:
            item["status"] = "completed" if ok else "failed"
            save_manifest(manifest)
            if ok:
                state["done"] += 1
                state["since_merge"] += 1
                if state["since_merge"] >= 5:
                    state["since_merge"] = 0
                    merge()
            else:
                state["failed"] += 1
                if state["failed"] >= 3:
                    state["stop"] = True
                    print("3 failures - draining, no new batches started "
                          "(check model/quota).")

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        for f in as_completed([ex.submit(job, i) for i in todo]):
            f.result()

    if state["done"]:
        merge()
    pending = sum(1 for i in manifest if i["status"] == "pending")
    print(f"\nRun done: {state['done']} completed, {state['failed']} failed, "
          f"{pending} still pending.")


if __name__ == "__main__":
    main()
