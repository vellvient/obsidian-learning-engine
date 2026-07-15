#!/usr/bin/env python3
"""Shared service layer for the Obsidian Learning Cockpit.

The vault remains canonical. This module reads exercise Markdown, the unified
question banks, the prerequisite edge store and FSRS state. Personal cockpit
state is kept separately in papers/cockpit_state.json and is gitignored.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import time
import uuid
from collections import defaultdict, deque
from contextlib import contextmanager
from pathlib import Path
from typing import Any

VAULT = Path(__file__).resolve().parent
CATALOG_PATH = VAULT / "config" / "course_catalog.json"
EDGE_PATH = (VAULT / ".engine" / "prerequisite_edges.json"
             if (VAULT / ".engine" / "prerequisite_edges.json").exists()
             else VAULT / ".hermes" / "prerequisite_edges_enriched.json")
CAUSAL_BRIDGES_PATH = VAULT / "config" / "causal_bridges.json"
SRS_PATH = VAULT / ".obsidian" / "srs_state.json"
STATE_PATH = VAULT / "papers" / "cockpit_state.json"
QUIZ_LOG_PATH = VAULT / "papers" / "quiz_log.json"
ERROR_LOG_PATH = (VAULT / "00 - Error Log.md" if (VAULT / "00 - Error Log.md").exists()
                  else VAULT / "00 - Math Error Log.md")
LOCK_PATH = VAULT / ".obsidian" / ".cockpit-state.lock"
ANSWER_TEX_PATH = VAULT / "papers" / "answers_tex.json"
QUESTION_BANK_PATH = VAULT / "papers" / "question_bank.json"
DEMO_BANK_PATH = VAULT / "papers" / "demo_question_bank.json"
TMUA_BANK_PATH = VAULT / "papers" / "tmua" / "question_bank.json"
RENDERS = VAULT / "papers" / "renders"
TMUA_RENDERS = VAULT / "papers" / "tmua" / "renders"
VISUAL_REFRESH_TIMEOUT = 120

MASTERY_RANK = {"not-started": 0, "attempted": 1, "familiar": 2,
                "proficient": 3, "mastered": 4}
RATING_NAMES = {1: "Again", 2: "Hard", 3: "Good", 4: "Easy"}
ERROR_TYPES = {"slip", "procedural", "concept", "prerequisite",
               "strategy", "misread", "unknown"}
ID_RE = re.compile(r"^(.*)_q(\d+)$")


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


@contextmanager
def state_lock(timeout: float = 5.0):
    """Best-effort cross-process lock with stale-lock recovery."""
    started = time.monotonic()
    while True:
        try:
            fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()} {time.time()}".encode("ascii"))
            os.close(fd)
            break
        except FileExistsError:
            try:
                if time.time() - LOCK_PATH.stat().st_mtime > 120:
                    LOCK_PATH.unlink()
                    continue
            except OSError:
                pass
            if time.monotonic() - started >= timeout:
                raise TimeoutError("The vault study state is busy; retry in a few seconds.")
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            LOCK_PATH.unlink()
        except FileNotFoundError:
            pass


def default_state() -> dict:
    catalog = read_json(CATALOG_PATH, {})
    profiles = list(catalog.get("profiles", {}))
    settings = {
        "deadline": catalog.get("deadline", "2027-12-31"),
        "weekly_hours": catalog.get("weekly_hours", 10),
        "courses": catalog.get("default_courses", profiles),
        "session_minutes": 150,
    }
    for course, profile in catalog.get("profiles", {}).items():
        routes = profile.get("routes", {})
        if routes:
            settings[f"route_{course}"] = catalog.get(f"default_{course}_route") or next(iter(routes))
    return {
        "version": 1,
        "settings": settings,
        "attempts": [], "errors": [], "timed_sets": [],
        "diagnostics": [], "sessions": [], "active_session": None,
    }


def load_state() -> dict:
    state = read_json(STATE_PATH, default_state())
    base = default_state()
    if not isinstance(state, dict):
        return base
    for key, value in base.items():
        state.setdefault(key, value)
    for key, value in base["settings"].items():
        state["settings"].setdefault(key, value)
    return state


def save_state(state: dict) -> None:
    atomic_json(STATE_PATH, state)


def parse_list(raw: str) -> list[int]:
    return [int(x) for x in re.findall(r"\d+", raw or "")]


def parse_nodes() -> dict[int, dict]:
    nodes: dict[int, dict] = {}
    for path in VAULT.glob("*.md"):
        match = re.match(r"^(\d+)\s+-\s+", path.name)
        if not match:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        fm_match = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
        fm = fm_match.group(1) if fm_match else ""
        def field(name: str, fallback: str = "") -> str:
            hit = re.search(rf"^{re.escape(name)}:\s*(.+)$", fm, re.M)
            return hit.group(1).strip().strip('"\'') if hit else fallback
        boxes = re.findall(r"^- \[([ xX])\]\s+([\w.-]+):?\s*(.*)$", text, re.M)
        done = sum(1 for checked, _sid, _desc in boxes if checked.lower() == "x")
        total = len(boxes)
        num = int(match.group(1))
        mastery = field("mastery", "not-started").lower()
        parents = re.findall(r"\[\[([^\]]+)\]\]", field("parents") or field("parent"))
        nodes[num] = {
            "id": num, "name": field("name", path.stem.split(" - ", 1)[-1]),
            "domain": field("domain", parents[0] if parents else "Uncategorised"),
            "topic": field("topic", ""), "mastery": mastery,
            "progress": {"done": done, "total": total, "pct": done / total if total else 0},
            "subskills": [{"id": sid, "description": desc.strip(),
                           "done": checked.lower() == "x"}
                          for checked, sid, desc in boxes],
            "prerequisites": parse_list(field("prerequisites")),
            "path": str(path),
        }
    return nodes


def load_edges() -> list[dict]:
    edges = read_json(EDGE_PATH, [])
    bridges = read_json(CAUSAL_BRIDGES_PATH, {}).get("edges", [])
    combined = edges + bridges
    return [e for e in combined if e.get("from") is not None and e.get("to") is not None]


def load_banks() -> list[dict]:
    primary = QUESTION_BANK_PATH if QUESTION_BANK_PATH.exists() else DEMO_BANK_PATH
    entries = read_json(primary, []) + read_json(TMUA_BANK_PATH, [])
    for entry in entries:
        entry["course"] = (entry.get("course") or entry.get("code") or "CIE").lower()
    return entries


def course_targets(settings: dict, banks: list[dict] | None = None) -> tuple[set[int], dict[str, set[int]]]:
    catalog = read_json(CATALOG_PATH, {})
    banks = banks if banks is not None else load_banks()
    profiles = catalog.get("profiles", {})
    selected = set(settings.get("courses") or profiles)
    by_course: dict[str, set[int]] = defaultdict(set)
    for course, profile in profiles.items():
        route_name = settings.get(f"route_{course}")
        route = profile.get("routes", {}).get(route_name, {}) if route_name else {}
        prefixes = set(route.get("component_prefixes", profile.get("component_prefixes", [])))
        code = str(profile.get("question_code", course)).lower()
        for entry in banks:
            entry_code = str(entry.get("code") or entry.get("course") or "").lower()
            component = str(entry.get("component") or "")
            if entry_code == code and (not prefixes or component[:1] in prefixes):
                by_course[course].update(int(x) for x in entry.get("topic_node_ids") or [])
        map_path = profile.get("map")
        if map_path:
            overlay = read_json(VAULT / map_path, {})
            for mapped in overlay.get("mappings", {}).values():
                by_course[course].update(int(x) for x in mapped)
            by_course[course].update(int(x) for x in overlay.get("new_nodes", {}).values())
        by_course[course].difference_update(int(x) for x in profile.get("target_exclusions", []))
        by_course[course].update(int(x) for x in profile.get("target_inclusions", []))
    target = set().union(*(by_course[c] for c in selected if c in by_course)) if selected else set()
    return target, dict(by_course)


def catalog_summary() -> dict:
    catalog = read_json(CATALOG_PATH, {})
    return {"title": catalog.get("title", "Learning Cockpit"),
            "deadline": catalog.get("deadline"),
            "mastery_gate": catalog.get("mastery_gate", {}), "profiles": {
        key: {"label": value.get("label", key), "routes": value.get("routes", {})}
        for key, value in catalog.get("profiles", {}).items()
    }}


def classify_layers(settings: dict, nodes: dict[int, dict] | None = None,
                    edges: list[dict] | None = None) -> tuple[dict[int, str], dict[str, set[int]]]:
    nodes = nodes or parse_nodes()
    edges = edges or load_edges()
    target, by_course = course_targets(settings)
    reverse: dict[int, set[int]] = defaultdict(set)
    for edge in edges:
        if edge.get("type", "HARD_PREREQ") in ("HARD_PREREQ", "SOFT_PREREQ"):
            reverse[int(edge["to"])].add(int(edge["from"]))
    support: set[int] = set()
    queue = deque(target)
    seen = set(target)
    while queue:
        child = queue.popleft()
        for parent in reverse.get(child, set()):
            if parent not in seen:
                seen.add(parent)
                support.add(parent)
                queue.append(parent)
    support -= target
    layers = {nid: ("target" if nid in target else "support" if nid in support else "enrichment")
              for nid in nodes}
    by_course["target"] = target
    by_course["support"] = support
    return layers, by_course


def review_evidence() -> dict[int, list[dict]]:
    state = read_json(SRS_PATH, {})
    out: dict[int, list[dict]] = defaultdict(list)
    for key, info in state.get("reviews", {}).items():
        hit = re.match(r"^(\d+)\s+-", key)
        if not hit:
            continue
        for event in (info.get("fsrs") or {}).get("history") or []:
            if event.get("rating") in (3, 4) and event.get("at"):
                out[int(hit.group(1))].append(event)
    for events in out.values():
        events.sort(key=lambda e: e["at"])
    return out


def node_status(node: dict, evidence: list[dict], errors: list[dict], gate: dict) -> str:
    if node["progress"]["pct"] < 1:
        return node.get("mastery", "not-started")
    dates = []
    for event in evidence:
        try:
            dates.append(dt.datetime.fromisoformat(event["at"].replace("Z", "+00:00")))
        except (ValueError, TypeError):
            pass
    recent_block = any(not e.get("resolved") and e.get("severity", 1) >= 3
                       for e in errors if int(e.get("node", -1)) == node["id"])
    if len(dates) >= 2 and (dates[-1] - dates[-2]).days >= gate.get("mastered_delay_days", 7) and not recent_block:
        return "mastered"
    if dates:
        return "proficient"
    return "familiar"


def progress_snapshot() -> dict:
    state = load_state()
    nodes = parse_nodes()
    layers, courses = classify_layers(state["settings"], nodes)
    evidence = review_evidence()
    gate = read_json(CATALOG_PATH, {}).get("mastery_gate", {})
    target = courses.get("target", set()) & set(nodes)
    statuses = {nid: node_status(nodes[nid], evidence.get(nid, []), state["errors"], gate)
                for nid in target}
    proficient = sum(MASTERY_RANK.get(s, 0) >= MASTERY_RANK["proficient"] for s in statuses.values())
    mastered = sum(s == "mastered" for s in statuses.values())
    domain: dict[str, list[int]] = defaultdict(list)
    for nid in target:
        domain[nodes[nid]["domain"]].append(nid)
    domain_scores = {name: round(100 * sum(MASTERY_RANK.get(statuses[n], 0) >= 3 for n in ids) / len(ids), 1)
                     for name, ids in domain.items() if ids}
    timed = [
        float(x.get("score_pct", 0))
        for x in state["timed_sets"]
        if x.get("completed") and int(x.get("questions_seen", x.get("attempted", 0)) or 0) > 0
    ]
    rolling = round(sum(timed[-3:]) / len(timed[-3:]), 1) if timed else 0.0
    deadline = dt.date.fromisoformat(state["settings"]["deadline"])
    days = max((deadline - dt.date.today()).days, 0)
    remaining = max(len(target) - proficient, 0)
    weekly_needed = remaining / max(days / 7, 1 / 7)
    hours = float(state["settings"].get("weekly_hours", 15))
    projected_capacity = max(hours * 0.45, 0.1)  # conservative proficient nodes/week
    status = "on-pace" if weekly_needed <= projected_capacity else "at-risk"
    if weekly_needed > projected_capacity * 1.5:
        status = "infeasible-at-current-hours"
    high_errors = sum(1 for e in state["errors"] if not e.get("resolved") and e.get("severity", 1) >= 3)
    gate_pass = (proficient == len(target) and mastered >= 0.95 * len(target)
                 and rolling >= gate.get("timed_average_pct", 85)
                 and (not domain_scores or min(domain_scores.values()) >= gate.get("domain_floor_pct", 75))
                 and high_errors == 0)
    return {
        "deadline": deadline.isoformat(), "days_left": days, "pace": status,
        "target_nodes": len(target), "support_nodes": sum(v == "support" for v in layers.values()),
        "proficient": proficient, "mastered": mastered,
        "proficient_pct": round(100 * proficient / len(target), 1) if target else 0,
        "mastered_pct": round(100 * mastered / len(target), 1) if target else 0,
        "weekly_nodes_needed": round(weekly_needed, 2), "timed_rolling_pct": rolling,
        "domain_scores": domain_scores, "high_errors": high_errors, "gate_pass": gate_pass,
    }


def ancestors(target: int, edges: list[dict], max_hops: int = 4) -> list[dict]:
    reverse: dict[int, list[dict]] = defaultdict(list)
    for edge in edges:
        if edge.get("type", "HARD_PREREQ") in ("HARD_PREREQ", "SOFT_PREREQ"):
            reverse[int(edge["to"])].append(edge)
    found: list[dict] = []
    queue = deque([(target, 0)])
    best = {target: 0}
    while queue:
        child, distance = queue.popleft()
        if distance >= max_hops:
            continue
        for edge in reverse.get(child, []):
            parent = int(edge["from"])
            nd = distance + 1
            if parent not in best or nd < best[parent]:
                best[parent] = nd
                found.append({"node": parent, "distance": nd, "edge_type": edge.get("type", "HARD_PREREQ"),
                              "reason": edge.get("reason", "")})
                queue.append((parent, nd))
    return found


def causal_recommendation(target: int) -> dict | None:
    """Return an explainable prerequisite intervention, never from one slip."""
    state = load_state()
    nodes = parse_nodes()
    if target not in nodes:
        return None
    attempts = [a for a in state["attempts"] if int(a.get("node", -1)) == target
                and a.get("grade") in ("wrong", "partial")]
    strong = [a for a in attempts if a.get("error_type") in ("concept", "prerequisite", "procedural")]
    if len(attempts) < 2 and not strong:
        return None
    candidates = ancestors(target, load_edges())
    if not candidates:
        return None
    text = " ".join(str(a.get("note", "")) + " " + str(a.get("failed_subskill", "")) for a in attempts).lower()
    text_words = set(re.findall(r"[a-z]{4,}", text))
    explicit_prerequisite = any(a.get("error_type") == "prerequisite" for a in attempts)
    ranked = []
    for item in candidates:
        node = nodes.get(item["node"])
        if not node:
            continue
        words = [w for w in re.findall(r"[a-z]{4,}", node["name"].lower())
                 if w not in {"using", "with", "from", "exam", "practice"}]
        text_hits = sum(
            any(w[:5] == token[:5] for token in text_words)
            for w in words
        )
        related_failures = sum(
            int(a.get("node", -1)) == node["id"] and a.get("grade") in ("wrong", "partial")
            for a in state["attempts"]
        )
        # A single vague target-level concept failure means “learn this target”,
        # not “pick an arbitrary ancestor”. One strong prerequisite signal,
        # matching intermediate-step language, or repeated evidence is required.
        if (len(attempts) < 2 and not explicit_prerequisite
                and text_hits == 0 and related_failures == 0):
            continue
        score = (4.0 if item["edge_type"] == "HARD_PREREQ" else 2.0) / item["distance"]
        score += (1 - node["progress"]["pct"]) * 3
        score += 5 * text_hits
        score += min(related_failures, 3) * 2
        ranked.append((score, item, node))
    if not ranked:
        return None
    score, item, node = max(ranked, key=lambda row: row[0])
    diagnostic = diagnostic_questions(node["id"], 3)
    return {
        "target": target, "target_name": nodes[target]["name"],
        "support": node["id"], "support_name": node["name"],
        "score": round(score, 2), "evidence_count": len(attempts),
        "reason": item["reason"] or f"{node['name']} is a prerequisite of {nodes[target]['name']}.",
        "estimated_minutes": 15, "diagnostic_question_ids": [q["id"] for q in diagnostic],
        "return_condition": "Pass at least 2 of 3 diagnostic questions, then retry the original target.",
    }


def question_renders(entry_id: str, markscheme: bool = False) -> list[str]:
    if entry_id.startswith("tmua_"):
        if markscheme:
            paths = sorted(TMUA_RENDERS.glob(f"{entry_id}_wa_p*.png"))
        else:
            path = TMUA_RENDERS / f"{entry_id}.png"
            paths = [path] if path.exists() else []
    else:
        match = ID_RE.match(entry_id)
        if not match:
            return []
        pattern = (f"{match.group(1)}_ms_q{match.group(2)}_p*.png" if markscheme
                   else f"{match.group(1)}_q{match.group(2)}_p*.png")
        paths = sorted(RENDERS.glob(pattern))
    return [str(p.relative_to(VAULT)).replace("\\", "/") for p in paths]


def decorate_question(entry: dict) -> dict:
    result = dict(entry)
    tex = read_json(ANSWER_TEX_PATH, {}).get(entry["id"], [])
    result["answers_tex"] = tex or entry.get("final_answers") or []
    result["question_images"] = question_renders(entry["id"])
    result["markscheme_images"] = question_renders(entry["id"], True)
    return result


def diagnostic_questions(node_id: int, count: int = 3,
                         exclude: set[str] | None = None) -> list[dict]:
    exclude = exclude or set()
    bank = [e for e in load_banks()
            if e.get("id") not in exclude
            and node_id in [int(x) for x in e.get("topic_node_ids") or []]]
    bank.sort(key=lambda e: ({"easy": 0, "medium": 1, "hard": 2}.get(e.get("difficulty"), 1), e.get("marks", 1)))
    return [decorate_question(e) for e in bank[:count]]


def get_question(entry_id: str) -> dict | None:
    for entry in load_banks():
        if entry.get("id") == entry_id:
            return decorate_question(entry)
    return None


def due_reviews(limit: int = 20) -> list[dict]:
    from srs_fsrs import VaultFSRS
    vault = VaultFSRS()
    result = []
    for key in vault.due_today()[:limit]:
        hit = re.match(r"^(\d+)\s+-\s+([^:]+)\.md:([^:]+):\s*(.*)$", key)
        result.append({"key": key, "node": int(hit.group(1)) if hit else None,
                       "label": hit.group(4) if hit else key})
    return result


def today_plan() -> dict:
    state = load_state()
    nodes = parse_nodes()
    layers, courses = classify_layers(state["settings"], nodes)
    target = courses.get("target", set()) & set(nodes)
    recommendations = []
    failed_targets = {int(a.get("node", -1)) for a in state["attempts"]
                      if a.get("grade") in ("wrong", "partial")}
    for nid in target & failed_targets:
        rec = causal_recommendation(nid)
        if rec:
            recommendations.append(rec)
    recommendations.sort(key=lambda x: (-x["score"], x["support"]))
    edges = load_edges()
    hard_prereqs: dict[int, set[int]] = defaultdict(set)
    target_children: dict[int, set[int]] = defaultdict(set)
    for edge in edges:
        parent, child = int(edge["from"]), int(edge["to"])
        if edge.get("type", "HARD_PREREQ") == "HARD_PREREQ":
            hard_prereqs[child].add(parent)
            if child in target:
                target_children[parent].add(child)
    question_counts: dict[int, int] = defaultdict(int)
    for entry in load_banks():
        for nid in entry.get("topic_node_ids") or []:
            question_counts[int(nid)] += 1
    unmet = []
    for nid in target:
        node = nodes[nid]
        if node["progress"]["pct"] >= 1:
            continue
        prereqs = hard_prereqs.get(nid, set(node["prerequisites"]))
        missing = [p for p in prereqs if p in nodes and nodes[p]["progress"]["pct"] < 1]
        if not missing:
            score = (100 if node["progress"]["pct"] > 0 else 0)
            score += min(question_counts.get(nid, 0), 30)
            score += 3 * len(target_children.get(nid, set()))
            score += min(nid / 1000, 1)
            unmet.append({"node": nid, "name": node["name"], "domain": node["domain"],
                          "layer": layers[nid], "progress": node["progress"],
                          "question_count": question_counts.get(nid, 0),
                          "unlock_count": len(target_children.get(nid, set())),
                          "score": round(score, 2)})
    unmet.sort(key=lambda x: (-x["score"], x["node"]))
    return {"progress": progress_snapshot(), "due": due_reviews(20),
            "remediation": recommendations[:5], "learn": unmet[:12],
            "active_session": state.get("active_session")}


def list_nodes(query: str = "", layer: str = "", course: str = "") -> list[dict]:
    state = load_state()
    nodes = parse_nodes()
    layers, courses = classify_layers(state["settings"], nodes)
    allowed = courses.get(course, set()) if course else set(nodes)
    query = query.lower().strip()
    result = []
    for nid, node in nodes.items():
        if nid not in allowed or (layer and layers[nid] != layer):
            continue
        if query and query not in f"{nid} {node['name']} {node['domain']}".lower():
            continue
        item = {k: v for k, v in node.items() if k != "path"}
        item["layer"] = layers[nid]
        item["courses"] = [c for c, ids in courses.items() if c not in ("target", "support") and nid in ids]
        result.append(item)
    return sorted(result, key=lambda n: (n["layer"] != "target", n["domain"], n["id"]))


def next_question(course: str = "", node: int | None = None, exclude: set[str] | None = None) -> dict | None:
    state = load_state()
    banks = load_banks()
    target, by_course = course_targets(state["settings"], banks)
    allowed = by_course.get(course, target) if course else target
    exclude = exclude or set()
    served = {a.get("id") for a in state["attempts"]}
    source = course.lower() if course and course.lower() != "all" else ""
    pool = [e for e in banks if e["id"] not in exclude
            and (not source or e.get("course") == source)
            and (node is None or node in e.get("topic_node_ids", []))
            and (node is not None or any(int(x) in allowed for x in e.get("topic_node_ids") or []))]
    pool.sort(key=lambda e: (e["id"] in served, {"easy": 0, "medium": 1, "hard": 2}.get(e.get("difficulty"), 1), e["id"]))
    return decorate_question(pool[0]) if pool else None


def record_attempt(payload: dict) -> dict:
    grade = payload.get("grade")
    if grade not in ("correct", "partial", "wrong", "skip"):
        raise ValueError("grade must be correct, partial, wrong or skip")
    error_type = payload.get("error_type", "unknown")
    if error_type not in ERROR_TYPES:
        error_type = "unknown"
    if grade in ("wrong", "partial"):
        if error_type == "unknown":
            raise ValueError("Choose the main error type before saving this attempt.")
        if not str(payload.get("note", "")).strip():
            raise ValueError("Write one short sentence describing what went wrong.")
    graded = 0
    remediation_outcome = None
    suppress_causal = bool(payload.get("diagnostic_for"))
    with state_lock():
        state = load_state()
        attempt_id = payload.get("attempt_id") or str(uuid.uuid4())
        if any(a.get("attempt_id") == attempt_id for a in state["attempts"]):
            return {"duplicate": True, "attempt_id": attempt_id}
        attempt = {
            "attempt_id": attempt_id, "id": payload["id"], "node": int(payload["node"]),
            "course": payload.get("course", ""), "grade": grade,
            "error_type": error_type, "failed_subskill": payload.get("failed_subskill", ""),
            "note": payload.get("note", ""), "duration_seconds": int(payload.get("duration_seconds", 0)),
            "ts": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "session_id": payload.get("session_id"), "diagnostic_for": payload.get("diagnostic_for"),
        }
        state["attempts"].append(attempt)
        if grade in ("wrong", "partial"):
            state["errors"].append({
                "id": str(uuid.uuid4()), "question_id": payload["id"], "node": int(payload["node"]),
                "error_type": error_type, "note": payload.get("note", ""),
                "severity": int(payload.get("severity", 2)), "resolved": False,
                "ts": attempt["ts"],
            })
        session = state.get("active_session")
        if session and session.get("id") == payload.get("session_id"):
            session.setdefault("attempt_ids", []).append(payload["id"])
            session.setdefault("attempt_record_ids", []).append(attempt_id)
            session.setdefault("sequence", []).append(payload["id"])
            remediation = session.get("remediation")
            if payload.get("diagnostic_for") and remediation and remediation.get("status") == "testing":
                remediation.setdefault("attempts", []).append({"id": payload["id"], "grade": grade})
                required = min(3, len(remediation.get("question_ids", [])))
                if required and len(remediation["attempts"]) >= required:
                    correct = sum(x["grade"] == "correct" for x in remediation["attempts"][:required])
                    passed = correct >= 2 if required >= 3 else correct == required
                    remediation.update({"status": "passed" if passed else "repair",
                                        "correct": correct, "required": required,
                                        "completed_at": attempt["ts"]})
                    session["phase"] = "return-to-target" if passed else "repair-support"
                    remediation_outcome = dict(remediation)
                    if passed:
                        for error in state["errors"]:
                            if (int(error.get("node", -1)) == int(remediation["target"])
                                    and not error.get("resolved")
                                    and error.get("error_type") in ("prerequisite", "procedural", "concept")):
                                error["resolved"] = True
                                error["resolved_at"] = attempt["ts"]
                                error["resolution"] = f"Passed support diagnostic for node {remediation['support']}"
            elif (remediation and remediation.get("status") == "passed"
                  and int(payload["node"]) == int(remediation["target"])):
                suppress_causal = True
                if grade == "correct":
                    remediation["status"] = "closed"
                    remediation["returned_at"] = attempt["ts"]
                    session["phase"] = "practice"
                else:
                    session["phase"] = "return-to-target"
            elif session.get("kind") == "guided":
                queue = [x for x in session.setdefault("retry_queue", []) if x.get("id") != payload["id"]]
                if grade in ("wrong", "partial"):
                    queue.append({"id": payload["id"], "after": len(session["sequence"]) + 2})
                session["retry_queue"] = queue
        save_state(state)
        # Keep the established CLI quiz history compatible.
        quiz = read_json(QUIZ_LOG_PATH, [])
        if not any(x.get("attempt_id") == attempt_id for x in quiz):
            quiz.append({"attempt_id": attempt_id, "id": payload["id"], "node": int(payload["node"]),
                         "course": payload.get("course", ""), "grade": grade, "ts": attempt["ts"]})
            atomic_json(QUIZ_LOG_PATH, quiz)
    if grade in ("correct", "wrong") and not payload.get("diagnostic_for"):
        from srs_fsrs import Rating, VaultFSRS
        with state_lock():
            vault = VaultFSRS()
            keys = []
            for key in vault.due_today():
                hit = re.match(r"^(\d+)\s+-", key)
                if hit and int(hit.group(1)) == int(payload["node"]):
                    keys.append(key)
            if grade == "wrong" and not keys:
                keys = [key for key, info in vault.state.get("reviews", {}).items()
                        if re.match(rf"^{int(payload['node'])}\s+-", key) and info.get("fsrs")][:1]
            for key in keys[:3]:
                if vault.grade_review(key, Rating.Good if grade == "correct" else Rating.Again):
                    graded += 1
            if graded:
                atomic_json(SRS_PATH, vault.state)
    if grade in ("wrong", "partial"):
        message = f"cockpit {grade} {payload['id']}"
        if payload.get("note"):
            message += f" - {payload['note']}"
        subprocess.run([sys.executable, str(VAULT / "log_error.py"), str(int(payload["node"])), message],
                       cwd=VAULT, capture_output=True, text=True, timeout=30, check=False)
    return {"attempt": attempt, "fsrs_graded": graded,
            "remediation": remediation_outcome,
            "causal": (causal_recommendation(int(payload["node"]))
                       if grade in ("wrong", "partial") and not suppress_causal else None)}


def grade_review(key: str, rating: int, session_id: str | None = None) -> dict:
    if rating not in (1, 2, 3, 4):
        raise ValueError("rating must be 1, 2, 3 or 4")
    from srs_fsrs import VaultFSRS
    with state_lock():
        vault = VaultFSRS()
        result = vault.grade_review(key, rating)
        if result is None:
            raise KeyError("review key not found")
        atomic_json(SRS_PATH, vault.state)
        state = load_state()
        session = state.get("active_session")
        if session_id and session and session.get("id") == session_id:
            reviewed = session.setdefault("reviewed_keys", [])
            if key not in reviewed:
                reviewed.append(key)
            save_state(state)
    return {"key": key, "rating": RATING_NAMES[rating], "due": result["due"].isoformat()}


def complete_subskill(node_id: int, subskill_id: str, done: bool) -> dict:
    nodes = parse_nodes()
    node = nodes.get(node_id)
    if not node:
        raise KeyError("node not found")
    path = Path(node["path"])
    text = path.read_text(encoding="utf-8", errors="replace")
    pattern = re.compile(rf"^(- \[)[ xX](\]\s+{re.escape(subskill_id)}:?\s+.*)$", re.M)
    updated, count = pattern.subn(rf"\g<1>{'x' if done else ' '}\g<2>", text, count=1)
    if count != 1:
        raise KeyError("subskill not found")
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(updated)
        os.replace(temp_name, path)
    finally:
        try: os.unlink(temp_name)
        except FileNotFoundError: pass
    return {"node": node_id, "subskill": subskill_id, "done": done}


def refresh_obsidian_visuals() -> dict:
    """Refresh generated Obsidian views without mutating graph.json or FIRe."""
    diagnostic_script = ("mathacademy_diagnostic.py"
                         if (VAULT / "mathacademy_diagnostic.py").exists()
                         else "flow_diagnostic.py")
    commands = [
        ("mastery_and_flow", [sys.executable, diagnostic_script, "--markdown"]),
        ("srs_tracker", [sys.executable, "srs_fsrs.py", "--tracker"]),
    ]
    outputs = {}
    errors = []
    started = time.monotonic()
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    for label, command in commands:
        script = VAULT / command[1]
        if not script.exists():
            errors.append(f"{label}: missing {script.name}")
            continue
        try:
            completed = subprocess.run(
                command, cwd=VAULT, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=VISUAL_REFRESH_TIMEOUT,
                check=False, creationflags=creationflags,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            errors.append(f"{label}: {exc}")
            continue
        output = "\n".join(part.strip() for part in (completed.stdout, completed.stderr) if part.strip())
        outputs[label] = output[-2000:]
        if completed.returncode != 0:
            errors.append(f"{label}: exited {completed.returncode}")
    mastery_changes = 0
    match = re.search(r"Synced\s+(\d+)\s+mastery tags", outputs.get("mastery_and_flow", ""), re.I)
    if match:
        mastery_changes = int(match.group(1))
    return {
        "ok": not errors,
        "mastery_changes": mastery_changes,
        "updated": [
            "exercise mastery tags and graph colours",
            "00 - Flow Zone Diagnostic.md", "00 - Review Grader.md",
            "00 - SRS Review Tracker.md",
        ] if not errors else [],
        "errors": errors,
        "duration_seconds": round(time.monotonic() - started, 2),
        "graph_json_untouched": True,
        "fire_untouched": True,
    }


def start_session(kind: str = "guided", course: str = "", minutes: int = 150) -> dict:
    if kind not in ("guided", "diagnostic", "timed"):
        raise ValueError("unknown session kind")
    with state_lock():
        state = load_state()
        if state.get("active_session") and state["active_session"].get("status") == "active":
            return state["active_session"]
        session = {"id": str(uuid.uuid4()), "kind": kind, "course": course,
                   "minutes": int(minutes), "started_at": dt.datetime.now().astimezone().isoformat(),
                   "status": "active", "phase": "review", "question_ids": [], "attempt_ids": [],
                   "attempt_record_ids": [], "sequence": [], "retry_queue": [],
                   "review_keys": [], "reviewed_keys": [], "remediation": None}
        if kind == "guided":
            plan = today_plan()
            session["review_keys"] = [item["key"] for item in plan["due"][:15]]
            _, by_course = course_targets(state["settings"])
            allowed = by_course.get(course, set()) if course else None
            for candidate in plan["learn"]:
                node_id = int(candidate["node"])
                if allowed is not None and node_id not in allowed:
                    continue
                question = next_question(course, node_id, set(session["question_ids"]))
                if question:
                    session["question_ids"].append(question["id"])
            if not session["question_ids"]:
                question = next_question(course)
                if question:
                    session["question_ids"].append(question["id"])
            session["phase"] = "review" if session["review_keys"] else "learn-practice"
        if kind == "diagnostic":
            nodes = list_nodes(layer="target", course=course)
            by_domain: dict[str, list[dict]] = defaultdict(list)
            for node in nodes: by_domain[node["domain"]].append(node)
            for domain_nodes in by_domain.values():
                for candidate in domain_nodes:
                    question = next_question(course, candidate["id"], set(session["question_ids"]))
                    if question:
                        session["question_ids"].append(question["id"])
                        break
            session["question_ids"] = session["question_ids"][:16]
            session["phase"] = "diagnostic"
        elif kind == "timed":
            count = max(5, min(40, round(minutes / 4)))
            for _ in range(count):
                question = next_question(course, exclude=set(session["question_ids"]))
                if not question: break
                session["question_ids"].append(question["id"])
            session["phase"] = "timed"
        state["active_session"] = session
        save_state(state)
    return session


def start_remediation(target: int) -> dict:
    recommendation = causal_recommendation(target)
    if not recommendation:
        raise ValueError("There is not enough evidence for a prerequisite diagnostic yet.")
    with state_lock():
        state = load_state()
        session = state.get("active_session")
        if not session or session.get("status") != "active":
            session = {"id": str(uuid.uuid4()), "kind": "guided", "course": "",
                       "minutes": 20, "started_at": dt.datetime.now().astimezone().isoformat(),
                       "status": "active", "phase": "remediation", "question_ids": [],
                       "attempt_ids": [], "sequence": [], "retry_queue": [], "remediation": None}
            state["active_session"] = session
        prior = session.get("remediation")
        depth = int(prior.get("depth", 0)) + 1 if prior and prior.get("target") != target else 1
        if depth > 2:
            raise ValueError("Prerequisite depth limit reached. Finish this repair block before diagnosing deeper.")
        question_ids = recommendation.get("diagnostic_question_ids") or []
        if not question_ids:
            raise ValueError("This support skill has no tagged diagnostic questions; open its note instead.")
        session["phase"] = "remediation"
        session["remediation"] = {
            "target": recommendation["target"], "target_name": recommendation["target_name"],
            "support": recommendation["support"], "support_name": recommendation["support_name"],
            "question_ids": question_ids[:3], "attempts": [], "status": "testing",
            "started_at": dt.datetime.now().astimezone().isoformat(),
            "estimated_minutes": recommendation["estimated_minutes"],
            "depth": depth, "root_target": prior.get("root_target", target) if prior else target,
            "history": [],
        }
        save_state(state)
    return session


def resume_remediation() -> dict:
    """Resume a confirmed support gap after a capped learning block."""
    with state_lock():
        state = load_state()
        session = state.get("active_session")
        remediation = session.get("remediation") if session else None
        if not remediation or remediation.get("status") != "repair":
            raise ValueError("There is no paused repair block to retest.")
        used = {str(item.get("id")) for item in remediation.get("attempts", [])}
        used.update(str(item) for item in remediation.get("question_ids", []))
        fresh = diagnostic_questions(int(remediation["support"]), 3, used)
        if not fresh:
            fresh = diagnostic_questions(int(remediation["support"]), 3)
        remediation.setdefault("history", []).append({
            "question_ids": list(remediation.get("question_ids", [])),
            "attempts": list(remediation.get("attempts", [])),
            "completed_at": remediation.get("completed_at"),
        })
        remediation["question_ids"] = [item["id"] for item in fresh]
        remediation["attempts"] = []
        remediation["status"] = "testing"
        remediation["round"] = int(remediation.get("round", 1)) + 1
        remediation["retest_started_at"] = dt.datetime.now().astimezone().isoformat()
        session["phase"] = "retest-support"
        save_state(state)
    return session


def finish_session() -> dict:
    with state_lock():
        state = load_state()
        session = state.get("active_session")
        if not session:
            return {"status": "none"}
        attempts = [a for a in state["attempts"] if a.get("session_id") == session["id"]]
        assessed = [a for a in attempts if a.get("grade") != "skip"]
        correct = sum(a.get("grade") == "correct" for a in attempts)
        partial = sum(a.get("grade") == "partial" for a in attempts)
        wrong = sum(a.get("grade") == "wrong" for a in attempts)
        skipped = sum(a.get("grade") == "skip" for a in attempts)
        score = round(100 * (correct + 0.5 * partial) / len(attempts), 1) if attempts else 0
        status = "completed" if attempts else "discarded"
        session.update({"status": status, "completed_at": dt.datetime.now().astimezone().isoformat(),
                        "questions_seen": len(attempts), "attempted": len(assessed),
                        "correct": correct, "partial": partial, "wrong": wrong,
                        "skipped": skipped, "score_pct": score})
        if attempts:
            state["sessions"].append(dict(session))
        if session["kind"] == "timed" and attempts:
            state["timed_sets"].append(dict(session, completed=True))
        elif session["kind"] == "diagnostic" and attempts:
            state["diagnostics"].append(dict(session))
        elif not attempts:
            session["discarded_reason"] = "No questions were graded."
        state["active_session"] = None
        save_state(state)
    if session.get("status") == "completed":
        visual_sync = refresh_obsidian_visuals()
        session["visual_sync"] = visual_sync
        with state_lock():
            state = load_state()
            for saved in reversed(state.get("sessions", [])):
                if saved.get("id") == session.get("id"):
                    saved["visual_sync"] = visual_sync
                    break
            state["last_visual_sync"] = {
                "completed_at": dt.datetime.now().astimezone().isoformat(),
                **visual_sync,
            }
            save_state(state)
    return session


def update_settings(changes: dict) -> dict:
    profiles = read_json(CATALOG_PATH, {}).get("profiles", {})
    allowed = {"deadline", "weekly_hours", "courses", "session_minutes"}
    allowed.update(f"route_{course}" for course in profiles)
    with state_lock():
        state = load_state()
        for key in allowed:
            if key in changes:
                state["settings"][key] = changes[key]
        save_state(state)
    return state["settings"]


def resolve_media(relative: str) -> Path:
    candidate = (VAULT / relative).resolve()
    if VAULT.resolve() not in candidate.parents or candidate.suffix.lower() not in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf"}:
        raise PermissionError("invalid media path")
    return candidate
