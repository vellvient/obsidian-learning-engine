#!/usr/bin/env python3
"""
micro_trainer.py
================
Generalized Cognitive Control Training (CCT) engine for mathematical
micro-schemas. This is the framework that `factor_pair_trainer.py` was the
prototype for: a single engine that can train ANY micro-schema, configured
declaratively through a `SchemaConfig`.

Design
------
* A `SchemaConfig` declares how to GENERATE a problem, DISPLAY it, CHECK the
  user's answer, and show the SOLUTION. The engine handles timing, adaptive
  speed pressure, spaced repetition (missed schemas re-surface sooner),
  persistence, and per-schema mastery tracking.
* Answer checking uses a randomized substitution trick: the displayed
  expression and the user's answer are both evaluated at several random
  integer points; if they agree everywhere, the answer is accepted. This means
  you never need a full symbolic parser -- any algebraically-equivalent answer
  is accepted, which is exactly what we want for fluency training.
* Detection mode (zerth1's "distraction schema" game) is supported natively:
  a schema may provide `detect_items` that yield (rule_text, is_valid) pairs;
  the user must judge VALID vs DISTRACTION under time pressure.

Usage
-----
    from schemas_algebra import ALGEBRA_SCHEMAS
    from micro_trainer import train
    train(ALGEBRA_SCHEMAS, num_problems=30)

Or via the CLI:  python train.py --list / python train.py --all / python train.py diff_squares
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")


import random
import time
import sys
import json
import re
import math
from collections import deque, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple


# ── Answer-equality engine (randomized substitution) ────────────────────────

_VAR_RE = re.compile(r"[a-zA-Z]")
_DIGIT_LETTER = re.compile(r"(\d)([a-zA-Z])")
_DIGIT_PAREN = re.compile(r"(\d)\(")
_PAREN_PAREN = re.compile(r"\)\s*\(")
_LETTER_PAREN = re.compile(r"([a-zA-Z])\(")


def preprocess(expr: str) -> str:
    """Turn casual math notation into evaluable Python arithmetic.

    Handles:  ^ -> **,  4x -> 4*x,  (a)(b) -> (a)*(b),  x(a) -> x*(a).
    Does NOT handle implicit letter-letter multiplication (xy -> x*y) on
    purpose -- our schema answers use single-letter variables or explicit
    coefficients, so this keeps parsing unambiguous.
    """
    s = expr.replace(" ", "").replace("·", "*").replace("×", "*")
    s = s.replace("^", "**")
    s = _DIGIT_LETTER.sub(r"\1*\2", s)
    s = _DIGIT_PAREN.sub(r"\1*(", s)
    s = _LETTER_PAREN.sub(r"\1*(", s)
    s = _PAREN_PAREN.sub(r")*(", s)
    return s


def _eval(expr: str, subs: Dict[str, int]) -> Optional[float]:
    try:
        code = preprocess(expr)
        val = eval(code, {"__builtins__": {}}, dict(subs))
        return val
    except Exception:
        return None


def vars_in(*exprs: str) -> List[str]:
    vs = set()
    for e in exprs:
        vs |= set(_VAR_RE.findall(e))
    return sorted(vs) or ["x"]


def answers_equal(correct_expr: str, user_expr: str, trials: int = 6) -> bool:
    """Return True iff the two expressions are algebraically equal over a set
    of random integer substitutions. Both sides must evaluate cleanly."""
    vs = vars_in(correct_expr, user_expr)
    for _ in range(trials):
        subs = {v: random.randint(2, 9) for v in vs}
        a = _eval(correct_expr, subs)
        b = _eval(user_expr, subs)
        if a is None or b is None:
            return False
        # compare with tolerance for float/int mix
        if abs(a - b) > 1e-9:
            return False
    return True


# ── Schema declaration ───────────────────────────────────────────────────────

@dataclass
class SchemaConfig:
    id: str
    name: str
    domain: str
    blurb: str
    # problem generator: difficulty level (0..N) -> problem dict
    generate: Callable[[int], dict]
    # render problem dict -> string shown to the user
    display: Callable[[dict], str]
    # canonical answer expression for verification + on-mistake display
    answer_expr: Callable[[dict], str]
    # the raw expression the user is transforming (for "must differ" check)
    source_expr: Callable[[dict], str] = lambda p: ""
    # True => user must produce a transformed form, not retype the input
    must_transform: bool = False
    # human-readable solution string
    solution: Callable[[dict], str] = lambda p: ""
    # difficulty label for stats
    difficulty_label: Callable[[dict], str] = lambda p: "default"
    # (rule_text, is_valid) pairs for detection mode (optional)
    detect_items: List[Tuple[str, bool]] = field(default_factory=list)
    # max difficulty level the generator understands
    max_level: int = 3


# ── Progress persistence ─────────────────────────────────────────────────────

PROGRESS_PATH = Path(__file__).parent / "progress.json"


def load_progress() -> dict:
    if PROGRESS_PATH.exists():
        try:
            return json.loads(PROGRESS_PATH.read_text())
        except Exception:
            return {}
    return {}


def save_progress(data: dict) -> None:
    PROGRESS_PATH.write_text(json.dumps(data, indent=2))


# ── The trainer ─────────────────────────────────────────────────────────────

class CCTTrainer:
    def __init__(
        self,
        schemas: List[SchemaConfig],
        num_problems: int = 24,
        start_time: float = 12.0,
        min_time: float = 3.0,
        max_time: float = 25.0,
        detect: bool = False,
    ):
        self.schemas = schemas
        self.by_id = {s.id: s for s in schemas}
        self.num_problems = num_problems
        self.detect = detect

        # per-schema adaptive time limit
        self.time_limit = {s.id: start_time for s in schemas}
        self.min_time = min_time
        self.max_time = max_time

        # per-schema counters
        self.correct = defaultdict(int)
        self.wrong = defaultdict(int)
        self.level = defaultdict(int)        # ramps with correct answers
        self.streak = defaultdict(int)
        self.times = defaultdict(list)       # recent correct response times
        self.misses = defaultdict(list)      # (source, user, answer) tuples

        self.results: List[dict] = []
        self.progress = load_progress()

    # ── difficulty ramping ──────────────────────────────────────────────────
    def _level_for(self, sid: str) -> int:
        lvl = self.level[sid]
        return min(lvl, self.by_id[sid].max_level)

    # ── main loop ───────────────────────────────────────────────────────────
    def run(self) -> None:
        print("\n" + "=" * 65)
        if self.detect:
            print("🔍 MICRO-SCHEMA DETECTION TRAINER")
            print("   Judge each rule: VALID or DISTRACTION (v / d)")
        else:
            print("🧠 MICRO-SCHEMA CCT TRAINER")
            print("   Build automaticity for algebraic micro-schemas.")
        print("=" * 65)
        print(f"Schemas: {len(self.schemas)}   Problems: {self.num_problems}")
        if not self.detect:
            print("Type your answer and press Enter. Adaptive time pressure on.")
        else:
            print("Say 'v' if the rule is a real micro-schema, 'd' if it's a fake.")
        print("-" * 65)
        try:
            input("Press Enter when ready...")
        except (EOFError, KeyboardInterrupt):
            print("\nSession cancelled.")
            sys.exit(0)
        print()

        # build a rotating queue of schema ids (spaced repetition)
        queue = deque(s.id for s in self.schemas)
        # pad the queue to cover num_problems
        q = deque()
        while len(q) < self.num_problems:
            q.extend(queue)
        q = deque(list(q)[: self.num_problems])

        for i in range(self.num_problems):
            sid = q.popleft()
            schema = self.by_id[sid]
            if self.detect:
                self._run_detect(i + 1, schema)
            else:
                self._run_problem(i + 1, schema, q)

        self._show_summary()
        self._persist()

    # ── production mode ─────────────────────────────────────────────────────
    def _run_problem(self, n: int, schema: SchemaConfig, queue: deque) -> None:
        level = self._level_for(schema.id)
        problem = schema.generate(level)
        source = schema.source_expr(problem)
        expected = schema.answer_expr(problem)

        print(f"\n─── Problem {n}/{self.num_problems} ───  [{schema.name}]")
        print("   " + schema.display(problem))
        print(f"   [limit {self.time_limit[schema.id]:.0f}s]")

        start = time.time()
        try:
            raw = input("   → ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nSession cancelled.")
            sys.exit(0)
        elapsed = time.time() - start

        if raw == "":
            correct = False
        else:
            ue = raw.replace(" ", "").replace("·", "*").replace("×", "*")
            correct = answers_equal(expected, ue)
            if correct and schema.must_transform and source:
                # reject trivial retyping of the input
                if preprocess(ue) == preprocess(source.replace(" ", "")):
                    correct = False
                    print("   ✗ That's just the input — produce the transformed form.")

        timed_out = elapsed > self.time_limit[schema.id] and not correct

        if correct:
            self.correct[schema.id] += 1
            self.streak[schema.id] += 1
            self.times[schema.id].append(elapsed)
            if len(self.times[schema.id]) > 12:
                self.times[schema.id].pop(0)
            emoji = "⚡" if elapsed < self.time_limit[schema.id] * 0.4 else "✅"
            print(f"   {emoji} Correct! ({elapsed:.1f}s)")
            # speed reward
            if self.streak[schema.id] >= 3 and self.time_limit[schema.id] > self.min_time:
                self.time_limit[schema.id] = max(
                    self.min_time, self.time_limit[schema.id] - 0.5
                )
                if self.streak[schema.id] == 3:
                    print(f"   🔥 Speed up! New limit {self.time_limit[schema.id]:.0f}s")
            # ramp difficulty
            self.level[schema.id] = min(schema.max_level, self.level[schema.id] + 1)
            queue.append(schema.id)  # rotate to back
        else:
            self.wrong[schema.id] += 1
            self.streak[schema.id] = 0
            sol = schema.solution(problem) or expected
            print(f"   ✗ Answer: {sol}")
            if timed_out:
                print(f"   ⏱ Time's up! ({elapsed:.1f}s > {self.time_limit[schema.id]:.0f}s)")
            # slow down + re-surface soon
            if self.time_limit[schema.id] < self.max_time:
                self.time_limit[schema.id] = min(
                    self.max_time, self.time_limit[schema.id] + 1.0
                )
            self.misses[schema.id].append(
                {"source": source, "user": raw, "answer": sol}
            )
            queue.insert(1, schema.id)  # re-surface near front (spaced rep)

        self.results.append({
            "schema": schema.id, "correct": correct, "time": elapsed,
            "timed_out": timed_out,
        })

    # ── detection mode ──────────────────────────────────────────────────────
    def _run_detect(self, n: int, schema: SchemaConfig) -> None:
        if not schema.detect_items:
            return
        rule, is_valid = random.choice(schema.detect_items)
        print(f"\n─── Probe {n}/{self.num_problems} ───  [{schema.name}]")
        print(f"   RULE: {rule}")
        start = time.time()
        try:
            raw = input("   valid (v) / distraction (d) → ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n\nSession cancelled.")
            sys.exit(0)
        elapsed = time.time() - start

        guess = raw in ("v", "valid", "1")
        correct = guess == is_valid
        if correct:
            self.correct[schema.id] += 1
            self.streak[schema.id] += 1
            self.times[schema.id].append(elapsed)
            emoji = "⚡" if elapsed < 2.0 else "✅"
            print(f"   {emoji} Right! ({elapsed:.1f}s)  [{'VALID' if is_valid else 'DISTRACTION'}]")
            if self.streak[schema.id] >= 3 and self.time_limit[schema.id] > self.min_time:
                self.time_limit[schema.id] = max(self.min_time, self.time_limit[schema.id] - 0.5)
        else:
            self.wrong[schema.id] += 1
            self.streak[schema.id] = 0
            truth = "VALID" if is_valid else "DISTRACTION"
            print(f"   ✗ It was {truth}.")
            self.misses[schema.id].append({"rule": rule, "was": truth})
        self.results.append({"schema": schema.id, "correct": correct, "time": elapsed})

    # ── summary + persistence ───────────────────────────────────────────────
    def _mastery(self, sid: str) -> float:
        times = self.times[sid]
        c, w = self.correct[sid], self.wrong[sid]
        total = c + w
        if total == 0:
            return 0.0
        acc = c / total
        # speed component: fraction of recent answers under 4s
        fast = sum(1 for t in times if t < 4.0) / max(len(times), 1)
        return round(100 * (0.6 * acc + 0.4 * fast), 1)

    def _show_summary(self) -> None:
        print("\n" + "=" * 65)
        print("📊 SESSION SUMMARY")
        print("=" * 65)
        total = len(self.results)
        correct = sum(1 for r in self.results if r["correct"])
        print(f"\n  Overall: {correct}/{total} ({correct/total*100:.0f}%)")
        print(f"\n  {'Schema':<22}{'Score':>10}{'Avg':>8}{'Mastery':>10}")
        print("  " + "-" * 50)
        for s in self.schemas:
            sid = s.id
            c, w = self.correct[sid], self.wrong[sid]
            t = self.times[sid]
            avg = f"{sum(t)/len(t):.1f}s" if t else "—"
            print(f"  {s.name:<22}{f'{c}/{c+w}':>10}{avg:>8}{self._mastery(sid):>9}%")
        # mistakes
        all_misses = [(sid, m) for sid in self.misses for m in self.misses[sid]]
        if all_misses:
            print(f"\n  Mistakes ({len(all_misses)}):")
            for sid, m in all_misses[:6]:
                if "source" in m:
                    print(f"    [{self.by_id[sid].name}] {m['source']} → {m['answer']}")
                else:
                    print(f"    [{self.by_id[sid].name}] {m['rule']} (was {m['was']})")

    def _persist(self) -> None:
        for s in self.schemas:
            sid = s.id
            rec = self.progress.setdefault(sid, {
                "name": s.name, "domain": s.domain,
                "sessions": 0, "total_correct": 0, "total_wrong": 0,
                "best_streak": 0, "fastest": None, "mastery": 0.0,
            })
            rec["sessions"] += 1
            rec["total_correct"] += self.correct[sid]
            rec["total_wrong"] += self.wrong[sid]
            rec["best_streak"] = max(rec["best_streak"], self.streak[sid])
            t = self.times[sid]
            if t:
                fastest = min(t)
                rec["fastest"] = fastest if rec["fastest"] is None else min(rec["fastest"], fastest)
            rec["mastery"] = max(rec["mastery"], self._mastery(sid))
        save_progress(self.progress)


# ── Convenience entry point ──────────────────────────────────────────────────

def train(schemas: List[SchemaConfig], num_problems: int = 24, detect: bool = False) -> None:
    CCTTrainer(schemas, num_problems=num_problems, detect=detect).run()


if __name__ == "__main__":
    # quick self-test when run directly
    from schemas_algebra import ALGEBRA_SCHEMAS
    bad = 0
    for s in ALGEBRA_SCHEMAS:
        if s.max_level == 0 and s.detect_items:
            continue  # detection-only schema, no generator
        for lvl in range(s.max_level + 1):
            for _ in range(50):
                p = s.generate(lvl)
                exp = s.answer_expr(p)
                if not answers_equal(exp, exp):
                    bad += 1
                # canonical answer must validate against itself
                if s.must_transform and s.source_expr(p):
                    if preprocess(exp.replace(" ", "")) == preprocess(s.source_expr(p).replace(" ", "")):
                        bad += 1
    print(f"self-test: {bad} anomalies across {len(ALGEBRA_SCHEMAS)} schemas")
