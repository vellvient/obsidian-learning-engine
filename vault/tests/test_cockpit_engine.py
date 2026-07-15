import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cockpit_engine as engine


def note(num, name, mastery="not-started", checked=False):
    mark = "x" if checked else " "
    return f'''---
num: {num}
name: "{name}"
domain: Algebra
mastery: {mastery}
prerequisites: []
---
## Subskills
- [{mark}] {num}a: Demonstrate {name}.
'''


class CockpitEngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "config").mkdir()
        (self.root / ".hermes").mkdir()
        (self.root / ".obsidian").mkdir()
        (self.root / "papers" / "tmua").mkdir(parents=True)
        (self.root / "papers" / "renders").mkdir()
        (self.root / "334 - Simplifying surds.md").write_text(note(334, "Simplifying surds"), encoding="utf-8")
        (self.root / "667 - Division of complex numbers.md").write_text(note(667, "Division of complex numbers", checked=True), encoding="utf-8")
        (self.root / "900 - Enrichment.md").write_text(note(900, "Enrichment"), encoding="utf-8")
        self.write("config/course_catalog.json", {
            "profiles": {"9709": {"question_code": "9709", "target_exclusions": [334], "routes": {
                "p1-p3-s1-m1": {"component_prefixes": ["1", "3", "4", "5"]},
                "p1-p3-s1-s2": {"component_prefixes": ["1", "3", "5", "6"]}}},
                "9231": {"question_code": "9231", "component_prefixes": ["1", "2", "3", "4"]}},
            "mastery_gate": {"mastered_delay_days": 7, "timed_average_pct": 85, "domain_floor_pct": 75}
        })
        self.write("config/tmua_course_map.json", {"mappings": {}, "new_nodes": {}})
        self.write(".hermes/prerequisite_edges_enriched.json", [
            {"from": 334, "to": 667, "type": "HARD_PREREQ", "reason": "Surd simplification is needed when simplifying complex-number moduli."}
        ])
        self.write("papers/question_bank.json", [
            {"id": "9709_q1", "code": "9709", "component": "31", "topic_node_ids": [667], "difficulty": "medium", "final_answers": ["1"]},
            {"id": "9709_surd", "code": "9709", "component": "31", "topic_node_ids": [334], "difficulty": "easy", "final_answers": ["sqrt(2)"]},
            {"id": "9709_s2", "code": "9709", "component": "61", "topic_node_ids": [900], "difficulty": "easy", "final_answers": ["0"]}
        ])
        self.write("papers/tmua/question_bank.json", [])
        self.write("papers/answers_tex.json", {})
        self.write("papers/quiz_log.json", [])
        self.write(".obsidian/srs_state.json", {"reviews": {}})
        self.write("config/causal_bridges.json", {"edges": []})
        names = ["VAULT", "CATALOG_PATH", "EDGE_PATH", "CAUSAL_BRIDGES_PATH", "SRS_PATH", "STATE_PATH", "QUIZ_LOG_PATH",
                 "ERROR_LOG_PATH", "LOCK_PATH", "ANSWER_TEX_PATH", "QUESTION_BANK_PATH", "TMUA_BANK_PATH",
                 "RENDERS", "TMUA_RENDERS"]
        values = [self.root, self.root/"config/course_catalog.json", self.root/".hermes/prerequisite_edges_enriched.json", self.root/"config/causal_bridges.json",
                  self.root/".obsidian/srs_state.json", self.root/"papers/cockpit_state.json", self.root/"papers/quiz_log.json",
                  self.root/"00 - Math Error Log.md", self.root/".obsidian/.cockpit-state.lock", self.root/"papers/answers_tex.json",
                  self.root/"papers/question_bank.json", self.root/"papers/tmua/question_bank.json", self.root/"papers/renders",
                  self.root/"papers/tmua/renders"]
        self.patches = [patch.object(engine, n, v) for n, v in zip(names, values)]
        for p in self.patches: p.start()
        self.due_patch = patch.object(engine, "due_reviews", return_value=[])
        self.due_mock = self.due_patch.start()
        self.run_patch = patch.object(engine.subprocess, "run")
        self.run_patch.start()
        self.write("papers/cockpit_state.json", engine.default_state())

    def tearDown(self):
        self.run_patch.stop()
        self.due_patch.stop()
        for p in reversed(self.patches): p.stop()
        self.tmp.cleanup()

    def write(self, relative, value):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) if not isinstance(value, str) else value, encoding="utf-8")

    def test_target_support_enrichment_are_separate(self):
        layers, courses = engine.classify_layers(engine.load_state()["settings"])
        self.assertEqual(layers[667], "target")
        self.assertEqual(layers[334], "support")
        self.assertEqual(layers[900], "enrichment")
        self.assertNotIn(334, courses["target"])

    def test_one_slip_does_not_trigger_remediation(self):
        state = engine.load_state()
        state["attempts"] = [{"node": 667, "grade": "wrong", "error_type": "slip", "note": "sign"}]
        engine.save_state(state)
        self.assertIsNone(engine.causal_recommendation(667))

    def test_one_vague_concept_failure_stays_on_target(self):
        state = engine.load_state()
        state["attempts"] = [{
            "node": 667, "grade": "wrong", "error_type": "concept",
            "note": "I do not know how to begin.",
        }]
        engine.save_state(state)
        self.assertIsNone(engine.causal_recommendation(667))

    def test_one_named_prerequisite_failure_can_trigger_diagnostic(self):
        state = engine.load_state()
        state["attempts"] = [{
            "node": 667, "grade": "wrong", "error_type": "concept",
            "note": "I cannot simplify the surd in the denominator.",
        }]
        engine.save_state(state)
        self.assertEqual(engine.causal_recommendation(667)["support"], 334)

    def test_repeated_surd_errors_recommend_support_node(self):
        state = engine.load_state()
        state["attempts"] = [
            {"node": 667, "grade": "wrong", "error_type": "procedural", "note": "could not simplify the surd"},
            {"node": 667, "grade": "partial", "error_type": "prerequisite", "note": "surd manipulation failed"},
        ]
        engine.save_state(state)
        rec = engine.causal_recommendation(667)
        self.assertEqual(rec["support"], 334)
        self.assertEqual(rec["target"], 667)
        self.assertEqual(len(rec["diagnostic_question_ids"]), 1)

    def test_route_switch_does_not_change_mastery_or_include_support(self):
        state = engine.load_state()
        state["settings"]["route_9709"] = "p1-p3-s1-m1"
        engine.save_state(state)
        first, _ = engine.course_targets(state["settings"])
        state["settings"]["route_9709"] = "p1-p3-s1-s2"
        second, _ = engine.course_targets(state["settings"])
        self.assertIn(667, first)
        self.assertNotIn(900, first)
        self.assertIn(900, second)
        self.assertNotIn(334, first)
        self.assertEqual(engine.parse_nodes()[667]["progress"]["done"], 1)

    def test_active_session_resumes(self):
        first = engine.start_session("guided", "9709", 90)
        second = engine.start_session("timed", "9709", 30)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(second["kind"], "guided")

    def test_guided_session_uses_ranked_queue_and_review_floor(self):
        self.due_mock.return_value = [
            {"key": "review-a", "node": 667, "label": "A"},
            {"key": "review-b", "node": 667, "label": "B"},
        ]
        session = engine.start_session("guided", "9709", 90)
        self.assertEqual(session["review_keys"], ["review-a", "review-b"])
        self.assertEqual(session["question_ids"][0], "9709_q1")
        self.assertEqual(session["phase"], "review")

    def test_duplicate_attempt_is_idempotent(self):
        payload = {"attempt_id": "same", "id": "9709_q1", "node": 667, "grade": "skip"}
        engine.record_attempt(payload)
        result = engine.record_attempt(payload)
        self.assertTrue(result["duplicate"])
        self.assertEqual(len(engine.load_state()["attempts"]), 1)

    def test_wrong_attempt_requires_classification_and_note(self):
        payload = {"attempt_id": "bad", "id": "9709_q1", "node": 667,
                   "grade": "wrong", "diagnostic_for": 999}
        with self.assertRaises(ValueError):
            engine.record_attempt(payload)
        payload["error_type"] = "concept"
        with self.assertRaises(ValueError):
            engine.record_attempt(payload)
        payload["note"] = "I do not know how to divide complex numbers."
        engine.record_attempt(payload)
        self.assertEqual(len(engine.load_state()["errors"]), 1)

    def test_empty_timed_session_is_discarded(self):
        engine.start_session("timed", "9709", 30)
        result = engine.finish_session()
        state = engine.load_state()
        self.assertEqual(result["status"], "discarded")
        self.assertEqual(state["timed_sets"], [])
        self.assertEqual(state["sessions"], [])

    def test_legacy_empty_timed_set_is_ignored_by_forecast(self):
        state = engine.load_state()
        state["timed_sets"] = [
            {"completed": True, "attempted": 0, "score_pct": 0},
            {"completed": True, "questions_seen": 2, "attempted": 2, "score_pct": 80},
        ]
        engine.save_state(state)
        self.assertEqual(engine.progress_snapshot()["timed_rolling_pct"], 80.0)

    def test_session_summary_counts_attempts_partials_and_skips(self):
        session = engine.start_session("timed", "9709", 30)
        common = {"session_id": session["id"], "diagnostic_for": 999, "node": 667}
        engine.record_attempt({**common, "attempt_id": "c", "id": "9709_q1", "grade": "correct"})
        engine.record_attempt({**common, "attempt_id": "p", "id": "9709_surd", "grade": "partial",
                               "error_type": "procedural", "note": "I could not finish the simplification."})
        engine.record_attempt({**common, "attempt_id": "s", "id": "9709_s2", "grade": "skip"})
        result = engine.finish_session()
        self.assertEqual(result["questions_seen"], 3)
        self.assertEqual(result["attempted"], 2)
        self.assertEqual(result["correct"], 1)
        self.assertEqual(result["partial"], 1)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["score_pct"], 50.0)
        self.assertEqual(len(engine.load_state()["timed_sets"]), 1)

    def test_finish_refreshes_obsidian_visuals_without_graph_or_fire(self):
        session = engine.start_session("guided", "9709", 30)
        engine.record_attempt({"attempt_id": "visual", "id": "9709_q1", "node": 667,
                               "grade": "correct", "session_id": session["id"]})
        refresh = {
            "ok": True, "mastery_changes": 1,
            "updated": ["exercise mastery tags and graph colours"],
            "errors": [], "graph_json_untouched": True, "fire_untouched": True,
        }
        with patch.object(engine, "refresh_obsidian_visuals", return_value=refresh) as mocked:
            result = engine.finish_session()
        mocked.assert_called_once_with()
        self.assertEqual(result["visual_sync"], refresh)
        state = engine.load_state()
        self.assertTrue(state["last_visual_sync"]["ok"])
        self.assertEqual(state["sessions"][-1]["visual_sync"], refresh)

    def test_empty_session_does_not_refresh_obsidian_visuals(self):
        engine.start_session("guided", "9709", 30)
        with patch.object(engine, "refresh_obsidian_visuals") as mocked:
            result = engine.finish_session()
        self.assertEqual(result["status"], "discarded")
        mocked.assert_not_called()

    def test_session_cursor_advances_and_remediation_can_pass(self):
        session = engine.start_session("guided", "9709", 90)
        engine.record_attempt({"attempt_id": "cursor", "id": "9709_q1", "node": 667,
                               "grade": "skip", "session_id": session["id"]})
        self.assertIn("9709_q1", engine.load_state()["active_session"]["attempt_ids"])
        state = engine.load_state()
        state["attempts"].extend([
            {"node": 667, "grade": "wrong", "error_type": "procedural", "note": "surd"},
            {"node": 667, "grade": "partial", "error_type": "prerequisite", "note": "surd"},
        ])
        state["errors"].append({"node": 667, "error_type": "prerequisite", "severity": 3, "resolved": False})
        engine.save_state(state)
        session = engine.start_remediation(667)
        result = engine.record_attempt({"attempt_id": "diag", "id": "9709_surd", "node": 334,
                                        "grade": "correct", "session_id": session["id"],
                                        "diagnostic_for": 667})
        self.assertEqual(result["remediation"]["status"], "passed")
        self.assertTrue(engine.load_state()["errors"][0]["resolved"])

    def test_failed_diagnostic_pauses_for_learning_then_retests(self):
        session = engine.start_session("guided", "9709", 90)
        state = engine.load_state()
        state["attempts"].extend([
            {"node": 667, "grade": "wrong", "error_type": "procedural", "note": "surd"},
            {"node": 667, "grade": "partial", "error_type": "prerequisite", "note": "surd"},
        ])
        engine.save_state(state)
        session = engine.start_remediation(667)
        failed = engine.record_attempt({
            "attempt_id": "diag-fail", "id": "9709_surd", "node": 334,
            "grade": "wrong", "error_type": "concept", "note": "I cannot simplify this surd.",
            "session_id": session["id"], "diagnostic_for": 667,
        })
        self.assertEqual(failed["remediation"]["status"], "repair")
        resumed = engine.resume_remediation()
        self.assertEqual(resumed["remediation"]["status"], "testing")
        self.assertEqual(resumed["remediation"]["round"], 2)
        passed = engine.record_attempt({
            "attempt_id": "diag-pass", "id": "9709_surd", "node": 334,
            "grade": "correct", "session_id": session["id"], "diagnostic_for": 667,
        })
        self.assertEqual(passed["remediation"]["status"], "passed")
        target_miss = engine.record_attempt({
            "attempt_id": "target-retry", "id": "9709_q1", "node": 667,
            "grade": "partial", "error_type": "procedural", "note": "The final simplification is still wrong.",
            "session_id": session["id"],
        })
        self.assertIsNone(target_miss["causal"])
        self.assertEqual(engine.load_state()["active_session"]["remediation"]["status"], "passed")


if __name__ == "__main__":
    unittest.main()
