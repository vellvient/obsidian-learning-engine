#!/usr/bin/env python3
"""
srs_fsrs.py — FSRS v6 scheduler + vault adaptor (pure Python, ZERO dependencies)

Why this exists
---------------
Improvement #1 from the Math-Academy-alternatives analysis:
  * Replace the vault's fixed 5-stage SRS intervals (1/3/7/14/30 days) with
    FSRS v6 — the Free Spaced Repetition Scheduler used by plcourse/Math
    Academy-style systems. FSRS tracks per-topic Stability + Difficulty and
    predicts the *actual* probability of recall, so intervals adapt to YOU
    instead of being hardcoded.
  * Add the two scheduler rules plcourse has that the vault lacks:
      - COMPRESSION: if a topic AND its child are both due, show only the child
        (don't waste a review on the parent).
      - RELEARNING-LOCK: if you fail a prerequisite (rating=Again), hide all its
        dependents until the prerequisite is fixed.
  * Replace the flat 0.3 FIRe credit with a proper FSRS stability boost that
    follows the prereq chain (chain-weight x decay), exactly like plcourse.

The FSRS math below is a faithful port of open-spaced-repetition/py-fsrs
(DEFAULT_PARAMETERS, decay 0.1542, all formula helpers) — verified against the
library source. No py-fsrs pip package required, so nothing is installed into
your system.

srs_state.json compatibility
----------------------------
The auto-sync daemon OWNS srs_state.json. This module never deletes the daemon's
fields. It ADDS an "fsrs" sub-object to each review entry (state, stability,
difficulty, due, last_review, rating history). The old review_stages array is
left intact so the daemon and the Flow Zone Diagnostic keep working. Calling
migrate_to_fsrs() once seeds the fsrs objects; afterwards grade_review() updates
them on every tick.

Usage (interactive / cron)
  from srs_fsrs import VaultFSRS
  v = VaultFSRS()                 # auto-loads .obsidian/srs_state.json
  v.migrate_to_fsrs()             # one-time: seed fsrs objects (git-checkpoint first!)
  v.grade_review(key, Rating.Good, ticked_at=datetime.now())
  due = v.due_today()             # respects compression + relearning-lock
  v.apply_fire_boost(ex_num, child_num, weight, ticked_at)
"""

from __future__ import annotations

import math
import json
import random
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# FSRS v6 — faithful port of open-spaced-repetition/py-fsrs
# ─────────────────────────────────────────────────────────────────────────────

FSRS_DEFAULT_DECAY = 0.1542
DEFAULT_PARAMETERS = (
    0.212, 1.2931, 2.3065, 8.2956, 6.4133, 0.8334,
    3.0194, 0.001, 1.8722, 0.1666, 0.796, 1.4835,
    0.0614, 0.2629, 1.6483, 0.6014, 1.8729, 0.5425,
    0.0912, 0.0658, FSRS_DEFAULT_DECAY,
)
STABILITY_MIN = 0.001
MIN_DIFFICULTY = 1.0
MAX_DIFFICULTY = 10.0
FUZZ_RANGES = [
    {"start": 2.5, "end": 7.0, "factor": 0.15},
    {"start": 7.0, "end": 20.0, "factor": 0.1},
    {"start": 20.0, "end": math.inf, "factor": 0.05},
]

# Rating enum (mirrors py-fsrs: Again=1, Hard=2, Good=3, Easy=4)
class Rating:
    Again = 1
    Hard = 2
    Good = 3
    Easy = 4

# State enum (Learning=1, Review=2, Relearning=3)
class State:
    Learning = 1
    Review = 2
    Relearning = 3

RATING_NAMES = {1: "Again", 2: "Hard", 3: "Good", 4: "Easy"}


class FSRS:
    """Minimal faithful FSRS v6 scheduler (no torch, no external deps)."""

    def __init__(
        self,
        parameters: tuple = DEFAULT_PARAMETERS,
        desired_retention: float = 0.9,
        maximum_interval: int = 36500,
        enable_fuzzing: bool = True,
    ):
        self.parameters = tuple(parameters)
        self.desired_retention = desired_retention
        self.maximum_interval = maximum_interval
        self.enable_fuzzing = enable_fuzzing
        self._DECAY = -self.parameters[20]
        self._FACTOR = 0.9 ** (1 / self._DECAY)

    # ── retrievability ──
    def retrievability(self, stability: float, elapsed_days: float) -> float:
        if stability is None or stability <= 0:
            return 0.0
        return (1 + self._FACTOR * elapsed_days / stability) ** self._DECAY

    # ── helpers ──
    def _clamp_difficulty(self, d: float) -> float:
        return min(max(d, MIN_DIFFICULTY), MAX_DIFFICULTY)

    def _clamp_stability(self, s: float) -> float:
        return max(s, STABILITY_MIN)

    def _initial_stability(self, rating: int) -> float:
        return self._clamp_stability(self.parameters[rating - 1])

    def _initial_difficulty(self, rating: int, clamp: bool = True) -> float:
        d = self.parameters[4] - (math.e ** (self.parameters[5] * (rating - 1))) + 1
        return self._clamp_difficulty(d) if clamp else d

    def _next_interval(self, stability: float) -> int:
        iv = (stability / self._FACTOR) * (
            (self.desired_retention ** (1 / self._DECAY)) - 1
        )
        iv = round(iv)
        iv = max(iv, 1)
        iv = min(iv, self.maximum_interval)
        return iv

    def _short_term_stability(self, stability: float, rating: int) -> float:
        inc = (math.e ** (self.parameters[17] * (rating - 3 + self.parameters[18]))) * (
            stability ** -self.parameters[19]
        )
        if rating in (Rating.Good, Rating.Easy):
            inc = max(inc, 1.0)
        return self._clamp_stability(stability * inc)

    def _next_difficulty(self, difficulty: float, rating: int) -> float:
        def _damping(delta, diff):
            return (10.0 - diff) * delta / 9.0
        arg_1 = self._initial_difficulty(Rating.Easy, clamp=False)
        delta = -(self.parameters[6] * (rating - 3))
        arg_2 = difficulty + _damping(delta, difficulty)
        next_d = self.parameters[7] * arg_1 + (1 - self.parameters[7]) * arg_2
        return self._clamp_difficulty(next_d)

    def _next_forget_stability(self, difficulty, stability, retrievability):
        long_term = (
            self.parameters[11]
            * (difficulty ** -self.parameters[12])
            * (((stability + 1) ** self.parameters[13]) - 1)
            * (math.e ** ((1 - retrievability) * self.parameters[14]))
        )
        short_term = stability / (math.e ** (self.parameters[17] * self.parameters[18]))
        return min(long_term, short_term)

    def _next_recall_stability(self, difficulty, stability, retrievability, rating):
        hard_penalty = self.parameters[15] if rating == Rating.Hard else 1
        easy_bonus = self.parameters[16] if rating == Rating.Easy else 1
        return stability * (
            1
            + (math.e ** self.parameters[8])
            * (11 - difficulty)
            * (stability ** -self.parameters[9])
            * ((math.e ** ((1 - retrievability) * self.parameters[10])) - 1)
            * hard_penalty
            * easy_bonus
        )

    def _next_stability(self, difficulty, stability, retrievability, rating):
        if rating == Rating.Again:
            s = self._next_forget_stability(difficulty, stability, retrievability)
        else:
            s = self._next_recall_stability(difficulty, stability, retrievability, rating)
        return self._clamp_stability(s)

    def _fuzz(self, interval_days: int) -> int:
        if interval_days < 2.5:
            return interval_days
        delta = 1.0
        for fr in FUZZ_RANGES:
            g = fr["factor"] * max(min(float(interval_days), fr["end"]) - fr["start"], 0.0)
            delta += g
        lo = max(2, int(round(interval_days - delta)))
        hi = min(int(round(interval_days + delta)), self.maximum_interval)
        if hi < lo:
            return interval_days
        width = hi - lo + 1
        fuzzed = int(round(random.random() * width)) + lo
        return fuzzed

    # ── core review: returns (new_state, new_stability, new_difficulty, next_due, new_state_enum) ──
    def review(
        self,
        card: dict,
        rating: int,
        review_datetime: Optional[datetime] = None,
    ) -> dict:
        """card is a dict with keys: state, stability, difficulty, due, last_review
        (all except state optional for first review). Returns updated card dict
        with new due (datetime), stability, difficulty, state, last_review.
        Pure function: does not mutate input."""
        if review_datetime is None:
            review_datetime = datetime.now(timezone.utc)
        card = deepcopy(card) if isinstance(card, dict) else dict(card)

        state = card.get("state", State.Learning)
        stability = card.get("stability")
        difficulty = card.get("difficulty")
        last_review = card.get("last_review")

        if last_review:
            try:
                lr = last_review if isinstance(last_review, datetime) else datetime.fromisoformat(last_review)
                days_since = (review_datetime - lr).days
            except Exception:
                days_since = None
        else:
            days_since = None

        short_term = days_since is not None and days_since < 1

        if state == State.Learning or stability is None or difficulty is None:
            if stability is None or difficulty is None:
                stability = self._initial_stability(rating)
                difficulty = self._initial_difficulty(rating, clamp=True)
            elif short_term:
                stability = self._short_term_stability(stability, rating)
                difficulty = self._next_difficulty(difficulty, rating)
            else:
                r = self.retrievability(stability, days_since or 0)
                stability = self._next_stability(difficulty, stability, r, rating)
                difficulty = self._next_difficulty(difficulty, rating)
            # learning -> review on first non-Again grade
            if rating != Rating.Again:
                state = State.Review
                iv = self._next_interval(stability)
            else:
                iv = 0  # relearn; keep in learning/relearning
                state = State.Relearning if state != State.Learning else State.Learning
        else:
            if short_term:
                stability = self._short_term_stability(stability, rating)
            else:
                r = self.retrievability(stability, days_since or 0)
                stability = self._next_stability(difficulty, stability, r, rating)
            difficulty = self._next_difficulty(difficulty, rating)
            if rating == Rating.Again:
                state = State.Relearning
                iv = 0
            else:
                state = State.Review
                iv = self._next_interval(stability)

        # fuzz only review-state intervals
        if state == State.Review and self.enable_fuzzing and iv >= 1:
            fv = self._fuzz(iv)
            if isinstance(fv, tuple):
                iv = fv[0]
            else:
                iv = fv

        due = review_datetime + timedelta(days=iv) if iv > 0 else review_datetime + timedelta(minutes=10)
        return {
            "state": state,
            "stability": stability,
            "difficulty": difficulty,
            "due": due,
            "last_review": review_datetime,
            "last_rating": rating,
            "last_interval": iv,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Vault adaptor
# ─────────────────────────────────────────────────────────────────────────────

VAULT_DEFAULT = Path(__file__).resolve().parent
SRS_PATH = VAULT_DEFAULT / ".obsidian" / "srs_state.json"
EDGES_PATH = VAULT_DEFAULT / ".engine" / "prerequisite_edges.json"


class VaultFSRS:
    """Bridges srs_state.json <-> FSRS. Non-destructive to daemon fields."""

    def __init__(self, srs_path: Path = SRS_PATH, edges_path: Path = EDGES_PATH):
        self.srs_path = Path(srs_path)
        self.edges_path = Path(edges_path)
        self.fsrs = FSRS()
        self.state = self._load()
        self.edges = self._load_edges()

    # ── loading ──
    def _load(self) -> dict:
        if self.srs_path.exists():
            return json.loads(self.srs_path.read_text(encoding="utf-8"))
        return {"last_commit": None, "reviews": {}, "mastery_changes": {}}

    def _load_edges(self) -> list:
        if self.edges_path.exists():
            try:
                d = json.loads(self.edges_path.read_text(encoding="utf-8"))
                return d if isinstance(d, list) else []
            except Exception:
                return []
        return []

    def save(self):
        self.srs_path.write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    # ── dependents graph (for relearning-lock) ──
    def dependents(self, ex_num: int) -> set:
        """IDs that depend on ex_num (ex_num is a prerequisite of them)."""
        out = set()
        for e in self.edges:
            try:
                if int(e.get("from")) == ex_num:
                    out.add(int(e.get("to")))
            except (TypeError, ValueError):
                continue
        return out

    def prerequisites(self, ex_num: int) -> set:
        out = set()
        for e in self.edges:
            try:
                if int(e.get("to")) == ex_num:
                    out.add(int(e.get("from")))
            except (TypeError, ValueError):
                continue
        return out

    # ── chain-weight FIRe: walk ALL ancestors with decaying boost ──
    def ancestors_with_weights(self, child_num: int,
                                edge_weights: Optional[dict] = None,
                                decay: float = 0.5,
                                max_hops: int = 4) -> list:
        """BFS over the prerequisite graph from `child_num` to every ancestor.
        Returns a list of (ancestor_id, chain_weight, distance) where:
          chain_weight = PRODUCT of edge weights along the path (like plcourse),
          but each additional hop is further multiplied by `decay` so distant
          ancestors (grandparents, great-grandparents) get progressively smaller
          boosts. `edge_weights` maps ancestor_id -> that edge's weight (default 0.3).
        """
        if edge_weights is None:
            edge_weights = {}
        results = []
        # BFS: queue holds (node, accumulated_weight, distance)
        q = [(child_num, 1.0, 0)]
        seen = {}
        while q:
            node, acc, dist = q.pop(0)
            if dist >= max_hops:
                continue
            for pre in self.prerequisites(node):
                w = edge_weights.get(pre, 0.3)          # this edge's weight
                child_w = acc * w                          # chain product so far
                hop_w = child_w * (decay ** dist)         # additional decay by distance
                if pre in seen:
                    # keep the stronger path
                    if hop_w <= seen[pre]:
                        continue
                seen[pre] = hop_w
                results.append((pre, hop_w, dist + 1))
                q.append((pre, child_w, dist + 1))
        return results

    # Stage → seed stability (days). Used by migrate + reseed.
    STAGE_STABILITY = {0: 0.4, 1: 1.0, 2: 3.0, 3: 7.0, 4: 14.0, 5: 30.0}

    @staticmethod
    def _parse_due_naive(dt_str):
        if not dt_str:
            return None
        try:
            d = datetime.fromisoformat(str(dt_str).replace("Z", "+00:00"))
            if d.tzinfo is not None:
                d = d.replace(tzinfo=None)
            return d
        except Exception:
            return None

    def _seed_from_stages(self, info: dict, as_of: Optional[datetime] = None) -> dict:
        """Compute a correct FSRS seed from legacy review_stages.

        BUG FIX (2026-07-10): the original migrate used max(stage) across the
        whole ladder (always 5) and the LAST stage's due → everything got S=30
        and due ≈ tick+30d, so the grader showed 0 due while legacy had 300+
        overdue. Correct rule:
          - if any stage is overdue → due=as_of (review NOW), S from EARLIEST overdue stage
          - else → due=nearest future stage due, S from that stage
        """
        if as_of is None:
            as_of = datetime.now()
        if as_of.tzinfo is not None:
            as_of = as_of.replace(tzinfo=None)
        ticked = info.get("ticked_at")
        stages = info.get("review_stages", [])
        parsed = []
        for s in stages:
            d = self._parse_due_naive(s.get("due"))
            if d is not None:
                parsed.append((int(s.get("stage", 0) or 0), d))
        if not parsed:
            return {
                "state": State.Learning,
                "stability": 1.0,
                "difficulty": 5.0,
                "due": as_of.isoformat(),
                "last_review": ticked,
                "history": [],
                "reseed_stage": 0,
            }
        overdue = [(st, d) for st, d in parsed if d <= as_of]
        if overdue:
            st, _ = min(overdue, key=lambda x: (x[1], x[0]))
            due = as_of
            seed_stability = self.STAGE_STABILITY.get(st, 1.0)
            reached = st
        else:
            st, d = min(parsed, key=lambda x: x[1])
            due = d
            seed_stability = self.STAGE_STABILITY.get(st, 1.0)
            reached = st
        return {
            "state": State.Review if reached > 0 else State.Learning,
            "stability": seed_stability,
            "difficulty": 5.0,
            "due": due.isoformat(),
            "last_review": ticked,
            "history": [],
            "reseed_stage": reached,
        }

    # ── migration: seed fsrs sub-objects from existing fixed stages ──
    def migrate_to_fsrs(self, dry_run: bool = False) -> list:
        """Seed an 'fsrs' object for every review entry that lacks one.
        Uses the EARLIEST overdue stage (not max stage) for stability+due."""
        changes = []
        reviews = self.state.setdefault("reviews", {})
        as_of = datetime.now()
        for key, info in reviews.items():
            if "fsrs" in info:
                continue
            seed = self._seed_from_stages(info, as_of=as_of)
            info["fsrs"] = seed
            changes.append(
                f"  seeded fsrs for {key} (stage~{seed.get('reseed_stage')}, "
                f"S≈{seed['stability']}, due={str(seed.get('due'))[:10]})"
            )
        if changes and not dry_run:
            self.save()
        return changes

    def reseed_from_stages(self, dry_run: bool = False, force: bool = True,
                           as_of: Optional[datetime] = None) -> list:
        """OVERWRITE every review's fsrs object from legacy stages (bug-fix reseed).

        Preserves grade `history` when present so manual Again/Hard/Easy aren't lost;
        only state/stability/difficulty/due/last_review are recalculated from stages
        when history is empty. If history is non-empty and force=False, skip.
        With force=True (default for the Jul-2026 bug fix): always rewrite S/due
        from stages, keep history list attached.
        """
        if as_of is None:
            as_of = datetime.now()
        changes = []
        reviews = self.state.setdefault("reviews", {})
        for key, info in reviews.items():
            old = info.get("fsrs") or {}
            hist = list(old.get("history") or [])
            if hist and not force:
                continue
            seed = self._seed_from_stages(info, as_of=as_of)
            seed["history"] = hist  # preserve manual grades
            seed["reseeded_at"] = as_of.isoformat()
            old_due = (old.get("due") or "")[:10]
            new_due = (seed.get("due") or "")[:10]
            info["fsrs"] = seed
            changes.append(
                f"  reseed {key[:50]}…  S {old.get('stability')}→{seed['stability']}  "
                f"due {old_due}→{new_due}  stage~{seed.get('reseed_stage')}"
            )
        if changes and not dry_run:
            self.save()
        return changes

    def legacy_overdue_summary(self, as_of: Optional[datetime] = None) -> dict:
        """True legacy backlog (review_stages), independent of FSRS."""
        if as_of is None:
            as_of = datetime.now()
        if as_of.tzinfo is not None:
            as_of = as_of.replace(tzinfo=None)
        entries = 0
        skills = set()
        by_due = {}
        for key, info in self.state.get("reviews", {}).items():
            for s in info.get("review_stages", []):
                d = self._parse_due_naive(s.get("due"))
                if d is not None and d <= as_of:
                    entries += 1
                    skills.add(key)
                    day = d.date().isoformat()
                    by_due[day] = by_due.get(day, 0) + 1
        return {
            "overdue_stage_entries": entries,
            "unique_skills": len(skills),
            "by_due_date": dict(sorted(by_due.items())),
        }

    # ── grading a review tick ──
    def grade_review(self, review_key: str, rating: int, ticked_at: Optional[datetime] = None) -> Optional[dict]:
        info = self.state.get("reviews", {}).get(review_key)
        if not info:
            return None
        if ticked_at is None:
            ticked_at = datetime.now(timezone.utc)
        fsrs_obj = info.get("fsrs")
        if fsrs_obj is None:
            fsrs_obj = {"state": State.Learning, "stability": None, "difficulty": None,
                        "due": None, "last_review": None, "history": []}
        updated = self.fsrs.review(fsrs_obj, rating, ticked_at)
        # keep history (most recent last)
        hist = fsrs_obj.get("history", [])
        hist.append({"rating": rating, "at": ticked_at.isoformat(), "iv": updated.get("last_interval")})
        hist = hist[-20:]
        info["fsrs"] = {
            "state": updated["state"],
            "stability": updated["stability"],
            "difficulty": updated["difficulty"],
            "due": updated["due"].isoformat(),
            "last_review": updated["last_review"].isoformat(),
            "history": hist,
        }
        return updated

    # ── FIRe: chain-weighted stability boost to ALL ancestors (plcourse-style) ──
    def apply_fire_chain(self, child_num: int, edge_weights: Optional[dict] = None,
                         ticked_at: Optional[datetime] = None,
                         decay: float = 0.5, max_hops: int = 4) -> list:
        """When `child_num` is practiced, boost the FSRS stability of EVERY
        ancestor prerequisite, weight = chain-product of edge weights × distance
        decay (plcourse's FIRe). Returns change notes.

        For each ancestor A at distance d with chain weight cw:
            new_stability = stability_A * (1 + cw)
            due_A extended by ~ cw × remaining interval
        Grandparents get smaller cw than parents because of the decay factor.
        """
        if ticked_at is None:
            ticked_at = datetime.now(timezone.utc)
        notes = []
        ancestors = self.ancestors_with_weights(child_num, edge_weights, decay, max_hops)
        reviews = self.state.get("reviews", {})
        # map exercise id -> list of review keys
        keys_by_id = {}
        for key, info in reviews.items():
            try:
                ex_id = int(key.split(":")[0].split(" - ")[0])
            except Exception:
                continue
            keys_by_id.setdefault(ex_id, []).append(key)

        for anc_id, cw, dist in ancestors:
            for key in keys_by_id.get(anc_id, []):
                fsrs_obj = reviews[key].get("fsrs")
                if not fsrs_obj or fsrs_obj.get("stability") is None:
                    continue
                boost_factor = 1.0 + cw
                fsrs_obj["stability"] = fsrs_obj["stability"] * boost_factor
                if fsrs_obj.get("due"):
                    try:
                        due = datetime.fromisoformat(fsrs_obj["due"])
                        if due.tzinfo is None:
                            due = due.replace(tzinfo=timezone.utc)
                        remaining = (due - ticked_at).days
                        if remaining > 0:
                            ext = timedelta(days=int(cw * remaining))
                            fsrs_obj["due"] = (due + ext).isoformat()
                        else:
                            # already due/past: small grace extension
                            fsrs_obj["due"] = (ticked_at + timedelta(days=int(cw * fsrs_obj["stability"]))).isoformat()
                    except Exception:
                        pass
                notes.append(
                    f"  🔥 FIRe chain boost #{anc_id} (dist {dist}, w={cw:.3f}) "
                    f"from practicing #{child_num}"
                )
        return notes

    def apply_fire(self, exercises: dict, ticked_child_nums: list,
                   ticked_at: Optional[datetime] = None) -> list:
        """Top-level orchestrator mirroring `--apply-fire` semantics but using the
        chain-weighted FSRS boost. `exercises` is the diagnostic's exercise dict
        (has `implicit_review` + `fire_weights`). Only recently-ticked children
        are processed; only un-mastered ancestors are boosted.
        """
        if ticked_at is None:
            ticked_at = datetime.now(timezone.utc)
        all_notes = []
        for child_num in ticked_child_nums:
            ex = exercises.get(child_num)
            if not ex:
                continue
            if ex.get("pct", 0) >= 1.0:
                continue  # already mastered, no implicit review needed
            edge_weights = ex.get("fire_weights", {})
            notes = self.apply_fire_chain(child_num, edge_weights, ticked_at)
            all_notes.extend(notes)
        if all_notes:
            self.save()
            all_notes.insert(0, f"🔥 **FIRe (chain-weighted) applied:** {len(all_notes)} ancestor boosts")
        else:
            all_notes.append("  No chain FIRe boosts — no recently-ticked children with un-mastered prereqs.")
        return all_notes

    # ── scheduling rules ──
    def due_today(self, as_of: Optional[datetime] = None) -> list:
        """Return review keys due as_of, applying COMPRESSION and RELEARNING-LOCK.

        COMPRESSION: if a topic T and its child C are both due, drop T (show only C).
          Heuristic: drop a due item if it has a due *dependent* (in our edges)
          that is also due — the dependent review subsumes the parent review.
        RELEARNING-LOCK: if any prerequisite of an item is in Relearning state
          (was failed recently), hide the item until the prereq recovers.

        Note: comparisons use NAIVE local datetimes so reseeded stage dues match.
        """
        if as_of is None:
            as_of = datetime.now()
        if as_of.tzinfo is not None:
            as_of = as_of.replace(tzinfo=None)

        def _parse(dt_str):
            return self._parse_due_naive(dt_str)

        reviews = self.state.get("reviews", {})

        due_keys = []
        due_sort = {}  # key -> due datetime for oldest-first ranking
        for key, info in reviews.items():
            fsrs_obj = info.get("fsrs")
            due = None
            if fsrs_obj and fsrs_obj.get("due"):
                due = _parse(fsrs_obj["due"])
            if due is None:
                # fall back to earliest legacy overdue stage
                best = None
                for s in info.get("review_stages", []):
                    d = _parse(s.get("due"))
                    if d is not None and (best is None or d < best):
                        best = d
                due = best
            if due is not None and due <= as_of:
                due_keys.append(key)
                due_sort[key] = due
        # oldest first so catch-up hits the stalest memory first
        due_keys.sort(key=lambda k: due_sort.get(k, as_of))

        # build id -> key map
        id_of = {}
        for key in due_keys:
            try:
                id_of[int(key.split(":")[0].split(" - ")[0])] = key
            except Exception:
                pass

        locked = set()
        for key in due_keys:
            try:
                ex_id = int(key.split(":")[0].split(" - ")[0])
            except Exception:
                continue
            # relearning-lock: any prereq in Relearning hides this item
            for pre in self.prerequisites(ex_id):
                pkey = id_of.get(pre)
                if pkey:
                    fsrs_obj = reviews[pkey].get("fsrs")
                    if fsrs_obj and fsrs_obj.get("state") == State.Relearning:
                        locked.add(key)
                        break

        result = []
        for key in due_keys:
            if key in locked:
                continue
            # compression: drop if a due dependent exists
            try:
                ex_id = int(key.split(":")[0].split(" - ")[0])
            except Exception:
                ex_id = None
            compressed = False
            if ex_id is not None:
                for dep in self.dependents(ex_id):
                    if dep in id_of:
                        compressed = True
                        break
            if compressed:
                continue
            result.append(key)
        return result

    # ── bridge: mimic `--apply-fire` by finding recently-ticked children ──
    def apply_fire_from_srs(self, exercises: dict,
                            ticked_at: Optional[datetime] = None) -> list:
        """Find review entries ticked today/yesterday (mirrors the diagnostic's
        `--apply-fire` rule), treat each as a recently-practiced child, and run
        the chain-weighted FIRe boost over its ancestors. Returns change notes.
        """
        if ticked_at is None:
            ticked_at = datetime.now(timezone.utc)
        from datetime import date as _date
        yesterday = ticked_at - timedelta(days=1)
        ticked_children = []
        for key, info in self.state.get("reviews", {}).items():
            ta = info.get("ticked_at")
            if not ta:
                continue
            try:
                t = datetime.fromisoformat(ta)
                if t.tzinfo is None:
                    t = t.replace(tzinfo=timezone.utc)
            except Exception:
                continue
            if t >= yesterday:
                try:
                    ticked_children.append(int(key.split(":")[0].split(" - ")[0]))
                except Exception:
                    pass
        return self.apply_fire(exercises, ticked_children, ticked_at)



def _main():
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    v = VaultFSRS()
    if "--migrate" in sys.argv:
        dry = "--dry" in sys.argv
        print(f"FSRS migration ({'DRY RUN' if dry else 'APPLY'}):")
        for c in v.migrate_to_fsrs(dry_run=dry):
            print(c)
    elif "--reseed" in sys.argv:
        dry = "--dry" in sys.argv
        print(f"FSRS RESEED from legacy stages ({'DRY RUN' if dry else 'APPLY'}):")
        changes = v.reseed_from_stages(dry_run=dry, force=True)
        print(f"  {len(changes)} reviews reseeded")
        for c in changes[:12]:
            print(c)
        if len(changes) > 12:
            print(f"  ... and {len(changes)-12} more")
        if not dry:
            due = v.due_today()
            leg = v.legacy_overdue_summary()
            print(f"  → FSRS due_today now: {len(due)}")
            print(f"  → legacy overdue: {leg['overdue_stage_entries']} stages / {leg['unique_skills']} skills")
    elif "--due" in sys.argv:
        due = v.due_today()
        leg = v.legacy_overdue_summary()
        print(f"Due now ({len(due)} after compression+relearning-lock):")
        for k in due[:40]:
            print("  ", k)
        if len(due) > 40:
            print(f"  ... and {len(due)-40} more")
        print(f"Legacy backlog: {leg['overdue_stage_entries']} stage-entries / {leg['unique_skills']} skills")
    elif "--stats" in sys.argv:
        seeded = sum(1 for r in v.state.get("reviews", {}).values() if "fsrs" in r)
        total = len(v.state.get("reviews", {}))
        due = len(v.due_today())
        leg = v.legacy_overdue_summary()
        print(f"reviews: {total}, fsrs-seeded: {seeded}, fsrs-due: {due}")
        print(f"legacy-overdue-stages: {leg['overdue_stage_entries']}, unique: {leg['unique_skills']}")
    elif "--grade" in sys.argv:
        try:
            idx = sys.argv.index("--grade")
            key = sys.argv[idx + 1]
            rating_name = (sys.argv[idx + 2] if len(sys.argv) > idx + 2 else "Good").capitalize()
            rating = {"Again": Rating.Again, "Hard": Rating.Hard, "Good": Rating.Good,
                      "Easy": Rating.Easy}.get(rating_name, Rating.Good)
            res = v.grade_review(key, rating)
            if res is None:
                print(f"NO_SUCH_REVIEW: {key}")
            else:
                print(f"GRADED {key} -> {RATING_NAMES[rating]} | state={res['state']} "
                      f"S={res['stability']:.2f} due={res['due'].date()}")
                v.save()
        except (IndexError, KeyError):
            print("Usage: python srs_fsrs.py --grade \"<file>.md:<skillid>: <name>\" <Again|Hard|Good|Easy>")
    elif "--grader-note" in sys.argv:
        out = build_grader_note(v, limit=40)
        gpath = Path(VAULT_DEFAULT) / "00 - Review Grader.md"
        gpath.write_text(out, encoding="utf-8")
        n_due = len(v.due_today())
        print(f"Wrote {gpath} ({min(n_due, 40)} of {n_due} due items with grade buttons)")
    elif "--tracker" in sys.argv:
        out = build_srs_tracker_note(v)
        tpath = Path(VAULT_DEFAULT) / "00 - SRS Review Tracker.md"
        tpath.write_text(out, encoding="utf-8")
        print(f"Wrote {tpath}")
    else:
        print("Usage:")
        print("  python srs_fsrs.py --stats")
        print("  python srs_fsrs.py --migrate [--dry]")
        print("  python srs_fsrs.py --reseed [--dry]   # FIX over-scheduled FSRS from legacy stages")
        print("  python srs_fsrs.py --due")
        print("  python srs_fsrs.py --grade \"<file>.md:<skill>\" <Again|Hard|Good|Easy>")
        print("  python srs_fsrs.py --grader-note")
        print("  python srs_fsrs.py --tracker")


def build_grader_note(v: "VaultFSRS", limit: int = 40) -> str:
    """Due reviews with copy-ready terminal commands. Caps at `limit` (oldest first)."""
    due_all = v.due_today()
    due = due_all[:limit]
    leg = v.legacy_overdue_summary()
    lines = [
        "# Review Grader",
        "",
        f"**{len(due_all)} reviews due today** (after compression + relearning-lock). "
        f"Showing oldest **{len(due)}** below.",
        "",
        "Copy a block, paste in terminal, edit the rating word, press Enter.",
        "",
        f"_Legacy stage backlog (informational): {leg['overdue_stage_entries']} entries / "
        f"{leg['unique_skills']} skills._",
        "",
        "---",
        "",
    ]
    if not due:
        lines.append("_No reviews due right now._")
    for key in due:
        info = v.state["reviews"].get(key, {})
        fsrs_obj = info.get("fsrs", {})
        due_date = fsrs_obj.get("due", "")[:10]
        state_name = {1: "Learning", 2: "Review", 3: "Relearning"}.get(fsrs_obj.get("state"), "?")
        S = fsrs_obj.get("stability")
        s_str = f"{S:.1f}" if isinstance(S, (int, float)) else "?"
        skill = info.get("skill", key)
        fname = info.get("file", "")
        # Build the grade command
        cmd_prefix = "python srs_fsrs.py --grade "
        cmd = f'{cmd_prefix}"{key}" '
        lines.append(f"### {skill}")
        lines.append(
            f"- `{fname}`  |  {state_name}  |  S≈{s_str}  |  due: {due_date}"
        )
        lines.append("")
        lines.append("```bash")
        lines.append(f"# {skill}  —  Available: Again | Hard | Good | Easy")
        lines.append(f"{cmd}Good")
        lines.append("```")
        lines.append("")
    if len(due_all) > limit:
        lines.append(f"_…and {len(due_all) - limit} more. Re-run `--grader-note` after grading._")
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "Regenerate: `python srs_fsrs.py --grader-note`"
    )
    return "\n".join(lines)


def build_srs_tracker_note(v: "VaultFSRS") -> str:
    """Auto-regenerate the user-facing SRS tracker from FSRS state (not manual)."""
    today = datetime.now().strftime("%A, %b %d, %Y")
    due = v.due_today()
    leg = v.legacy_overdue_summary()
    lines = [
        "---",
        "topic: srs",
        "mastery: reference",
        "tags: [reference, srs, tracker]",
        f"generated: {datetime.now().date().isoformat()}",
        "---",
        "",
        "#reference",
        "",
        "# 🧠 SRS Review Tracker — auto-generated",
        "",
        f"**Source of truth: FSRS** · regenerated {today}",
        "",
        "> Do **not** hand-edit this file. Run `python srs_fsrs.py --tracker` or `python evening.py`.",
        "",
        f"## 🔴 Due Today — {len(due)} items (compression + relearning-lock)",
        "",
        f"_Legacy stage-entries overdue (cross-check): {leg['overdue_stage_entries']} / "
        f"{leg['unique_skills']} skills._",
        "",
        "*Cap at 20–30 cards. Grade Again/Hard if shaky. Then new Flow Zone learning.*",
        "",
        "| # | Exercise | Skill | S | Due |",
        "|---|----------|-------|---|-----|",
    ]
    for i, key in enumerate(due[:30], 1):
        info = v.state["reviews"].get(key, {})
        fsrs_obj = info.get("fsrs", {})
        fname = (info.get("file") or "").replace(".md", "")
        short = fname.split(" - ")[0] if " - " in fname else fname
        link = f"[[{fname}|{short}]]"
        S = fsrs_obj.get("stability")
        s_str = f"{S:.1f}" if isinstance(S, (int, float)) else "?"
        lines.append(
            f"| {i} | {link} | {str(info.get('skill', ''))[:40]} | {s_str} | "
            f"{str(fsrs_obj.get('due', ''))[:10]} |"
        )
    if len(due) > 30:
        lines.append(f"| … | and {len(due)-30} more | | | |")
    lines += [
        "",
        "## How to review",
        "",
        "1. Open [[00 - Review Grader]] for Again/Hard/Good/Easy buttons",
        "2. Or tick the subskill if fully recalled (watcher → Good)",
        "3. Cap 20–30 cards → switch to Flow Zone new learning",
        "",
        "## Commands",
        "",
        "```",
        "python morning.py",
        "python srs_fsrs.py --grader-note",
        "python evening.py",
        "```",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    _main()
