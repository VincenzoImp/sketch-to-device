"""Behavioral acceptance and malformed-input checks for the host reference."""

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import unittest

from runtime.reference import ReferenceRuntime
from runtime.scenarios import run_scenario
from runtime.validation import CAPABILITIES, INT_MAX, ValidationError, decode_json, package_report, parse_app


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "contracts/fixtures"
SCENARIOS = ROOT / "contracts/scenarios"


def fixture(name="tap-sprint"):
    return json.loads((FIXTURES / (name + ".json")).read_text())


def encode(app):
    return json.dumps(app).encode("utf-8")


def widget(app, name):
    return next(w for screen in app["screens"] for w in screen["widgets"] if w["id"] == name)


class ValidationTests(unittest.TestCase):
    def assert_invalid(self, app, code):
        with self.assertRaises(ValidationError) as caught:
            parse_app(app if isinstance(app, bytes) else encode(app))
        self.assertEqual(caught.exception.code, code)

    def test_both_packages_and_exact_byte_hash(self):
        for path in FIXTURES.glob("*.json"):
            raw = path.read_bytes()
            report = package_report(raw)
            self.assertEqual(report["sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(report["size_bytes"], len(raw))
            self.assertNotEqual(report["sha256"], package_report(raw + b" ")["sha256"])

    def test_button_colors_strict_and_optional(self):
        app = fixture()
        for color in ("#000000", "#FFFFFF", "#ff69b4", "#aBcDeF"):
            widget(app, "start")["background_color"] = color
            self.assertEqual(widget(parse_app(encode(app)), "start")["background_color"], color)
        for color in (None, 0, True, [], {}, "pink", "#fff", "#12345678", "#zz1234", "#123456\n", " #123456", "#１２３４５６"):
            widget(app, "start")["background_color"] = color
            with self.subTest(color=color):
                self.assert_invalid(app, "color")
        for name in ("score_live", "round_timer"):
            app = fixture()
            widget(app, name)["background_color"] = "#FF69B4"
            self.assert_invalid(app, "unknown_field")
        # Old packages keep their palette; color adds no required field.
        self.assertNotIn("background_color", widget(parse_app(encode(fixture())), "start"))

    def test_color_cycle_returns_to_pink_and_keeps_one_button(self):
        app = fixture("hello-colors")
        runtime = ReferenceRuntime(encode(app))
        expected = [("pink", "#FF69B4"), ("blue", "#164EAD"), ("green", "#80FF80"), ("pink", "#FF69B4")]
        for tick, (screen_id, color) in enumerate(expected):
            self.assertEqual(runtime.screen, screen_id)
            screen = next(s for s in app["screens"] if s["id"] == runtime.screen)
            self.assertEqual(len(screen["widgets"]), 1)
            button = screen["widgets"][0]
            self.assertEqual((button["text"], button["background_color"]), ("Hello World", color))
            runtime.press(button["id"], tick + 1, runtime.event_token())
            self.assertFalse(runtime.errors)

    def test_byte_limit_accepts_boundary_and_rejects_next_byte(self):
        raw = encode(fixture())
        boundary = raw + b" " * (65536 - len(raw))
        self.assertEqual(parse_app(boundary)["name"], "Tap Sprint")
        self.assert_invalid(boundary + b" ", "bytes")

    def test_depth_limit_before_object_tree_and_strings_not_containers(self):
        self.assertEqual(decode_json(b"[" * 12 + b"0" + b"]" * 12), [[[[[[[[[[[[0]]]]]]]]]]]])
        with self.assertRaises(ValidationError) as caught:
            decode_json(b"[" * 13 + b"0" + b"]" * 13)
        self.assertEqual(caught.exception.code, "depth")
        self.assertEqual(decode_json(b'"[[[\\\"{{{"'), '[[["{{{')

    def test_duplicate_keys_including_unicode_escapes(self):
        self.assert_invalid(b'{"state":{"score":1,"sc\\u006fre":2}}', "duplicate_key")

    def test_bad_json_utf8_nonfinite_fraction_and_bom(self):
        for raw, code in [(b'{', "json"), (b'\xff', "encoding"), (b'NaN', "number"),
                          (b'Infinity', "number"), (b'1.0', "number"), (b'1e0', "number"),
                          (b'\xef\xbb\xbf{}', "json")]:
            with self.subTest(raw=raw):
                self.assert_invalid(raw, code)

    def test_unknown_fields_all_object_levels(self):
        for target in [lambda a: a, lambda a: a["target"], lambda a: a["theme"],
                       lambda a: a["screens"][0], lambda a: widget(a, "start"),
                       lambda a: widget(a, "start")["on_press"][0]]:
            app = fixture()
            target(app)["script"] = "unsupported"
            self.assert_invalid(app, "unknown_field")

    def test_integer_fields_never_accept_boolean(self):
        for mutate in [lambda a: a.update(schema_version=True), lambda a: a.update(version=True),
                       lambda a: a["target"].update(width=True),
                       lambda a: widget(a, "round_timer").update(duration_seconds=True),
                       lambda a: widget(a, "tap")["on_press"][0].update(amount=True)]:
            app = fixture()
            mutate(app)
            self.assert_invalid(app, "integer")

    def test_state_type_references_and_set_preservation(self):
        for replacement in [True, "not_an_integer", INT_MAX + 1]:
            app = fixture()
            app["state"]["score"] = replacement
            self.assert_invalid(app, "reference" if replacement is True else "integer")
        app = fixture()
        widget(app, "start")["on_press"][0]["value"] = False
        self.assert_invalid(app, "type")
        app = fixture("focus-timer")
        widget(app, "done_toggle")["state_key"] = "missing"
        self.assert_invalid(app, "reference")

    def test_identifier_rules_and_unique_widget_ids_across_screens(self):
        for invalid in ["Upper", "1first", "a" * 49, "lower\n", "has space", "café"]:
            app = fixture()
            app["app_id"] = invalid
            self.assert_invalid(app, "identifier")
        app = fixture()
        widget(app, "score_final")["id"] = "score_live"
        self.assert_invalid(app, "duplicate_id")
        app = fixture()
        app["screens"][1]["id"] = "ready"
        self.assert_invalid(app, "duplicate_id")

    def test_missing_initial_navigation_and_timer_references(self):
        for mutate in [lambda a: a.update(initial_screen="missing"),
                       lambda a: widget(a, "start")["on_press"][3].update(screen_id="missing"),
                       lambda a: widget(a, "start")["on_press"][1].update(widget_id="tap")]:
            app = fixture()
            mutate(app)
            self.assert_invalid(app, "reference")

    def test_timer_completion_restrictions_and_malformed_handler(self):
        for kind in ["timer_start", "timer_pause", "timer_reset"]:
            app = fixture()
            widget(app, "round_timer")["on_complete"] = [{"type": kind, "widget_id": "round_timer"}]
            self.assert_invalid(app, "completion_action")
        for bad in (None, False, 1, "invalid", {}):
            for event, name in (("on_complete", "round_timer"), ("on_press", "start")):
                app = fixture()
                widget(app, name)[event] = bad
                with self.subTest(event=event, bad=bad):
                    self.assert_invalid(app, "count")
        for bad in (None, False, 1, "invalid", []):
            app = fixture()
            widget(app, "round_timer")["on_complete"] = [bad]
            with self.subTest(action=bad):
                self.assert_invalid(app, "type")

    def test_action_limit_and_unknown_action(self):
        app = fixture()
        widget(app, "start")["on_press"].append({"type": "navigate", "screen_id": "play"})
        self.assert_invalid(app, "count")
        app = fixture()
        widget(app, "tap")["on_press"] = [{"type": "execute"}]
        self.assert_invalid(app, "enum")

    def test_state_screen_widget_timer_resource_counts(self):
        app = fixture()
        app["state"] = {"v{}".format(i): 0 for i in range(17)}
        self.assert_invalid(app, "state")
        app = fixture()
        app["screens"] *= 3
        self.assert_invalid(app, "count")
        app = fixture()
        app["screens"][0]["widgets"] *= 5
        self.assert_invalid(app, "count")
        app = fixture()
        for name in ("extra_one", "extra_two"):
            app["screens"][0]["widgets"].append({"id": name, "type": "timer", "duration_seconds": 1, "on_complete": []})
        self.assert_invalid(app, "count")
        app = fixture()
        app["screens"] = [{"id": "s{}".format(i), "title": "Screen", "widgets": [
            {"id": "w{}_{}".format(i, j), "type": "label", "text": "Text"} for j in range(7)
        ]} for i in range(5)]
        self.assert_invalid(app, "count")

    def test_duration_version_and_state_boundaries(self):
        app = fixture()
        for duration in (1, 3600):
            widget(app, "round_timer")["duration_seconds"] = duration
            parse_app(encode(app))
        for duration in (0, 3601):
            widget(app, "round_timer")["duration_seconds"] = duration
            self.assert_invalid(app, "integer")
        for version in (0, INT_MAX + 1):
            app = fixture()
            app["version"] = version
            self.assert_invalid(app, "integer")
        app = fixture()
        app["state"].update(low=-(2 ** 31), high=INT_MAX, flag=True)
        parse_app(encode(app))

    def test_completion_only_result_reachable_but_orphan_rejected(self):
        parse_app(encode(fixture()))  # Result is reached only through timer completion.
        app = fixture()
        app["screens"].append({"id": "orphan", "title": "Orphan", "widgets": []})
        self.assert_invalid(app, "unreachable")

    def test_text_charset_name_limit_and_layout_overflow(self):
        for invalid in ("", "café", "new\nline", "x" * 49):
            app = fixture()
            app["name"] = invalid
            self.assert_invalid(app, "text")
        app = fixture()
        widget(app, "intro")["text"] = "x" * 121
        self.assert_invalid(app, "text")
        app = fixture()
        app["screens"][0]["widgets"] = [
            {"id": "text{}".format(i), "type": "label", "text": "x" * 120} for i in range(3)
        ]
        self.assert_invalid(app, "layout")

    def test_schema_artifacts_are_versioned_and_match_capability_presets(self):
        schema = json.loads((ROOT / "contracts/app.schema.json").read_text())
        self.assertEqual(schema["properties"]["schema_version"]["const"], 1)
        self.assertEqual(set(schema["properties"]["theme"]["properties"]["palette"]["enum"]), set(CAPABILITIES["palettes"]))
        self.assertFalse(CAPABILITIES["physical_layout_verified"])

    def test_schema_patterns_reject_final_newline_and_carriage_return(self):
        schema = json.loads((ROOT / "contracts/app.schema.json").read_text())
        patterns = [(schema["$defs"]["id"]["pattern"], "app_1-demo"),
                    (schema["$defs"]["text"]["pattern"], "A valid title!"),
                    (schema["properties"]["name"]["pattern"], "Tap Sprint")]
        for pattern, valid in patterns:
            with self.subTest(pattern=pattern):
                self.assertIsNotNone(re.search(pattern, valid))
                for suffix in ("\n", "\r", "\r\n"):
                    self.assertIsNone(re.search(pattern, valid + suffix))


class RuntimeTests(unittest.TestCase):
    def runtime(self, app=None):
        return ReferenceRuntime(encode(fixture() if app is None else app))

    def press(self, rt, widget_id, at):
        return rt.press(widget_id, at, rt.event_token())

    def test_three_taps_deadline_and_replay(self):
        rt = self.runtime()
        self.assertEqual(self.press(rt, "start", 0), "applied")
        for at in (1, 5000, 9999):
            self.press(rt, "tap", at)
        queued = rt.event_token()
        self.assertEqual(rt.press("tap", 10000, queued), "ignored")
        self.assertEqual((rt.screen, rt.state["score"]), ("result", 3))
        self.press(rt, "again", 15000)
        self.assertEqual((rt.screen, rt.state["score"]), ("play", 0))
        self.assertEqual(rt.snapshot()["timers"]["round_timer"]["remaining_ms"], 10000)
        self.assertEqual(rt.press("tap", 15001, queued), "ignored")

    def test_scheduler_completes_without_input_and_polling_does_not_restart(self):
        rt = self.runtime()
        self.press(rt, "start", 100)
        rt.advance(10100)
        self.assertEqual(rt.screen, "result")
        entry = rt.screen_entry
        rt.advance(10100)
        rt.advance(50000)
        self.assertEqual(rt.screen_entry, entry)
        self.assertEqual(rt.snapshot()["timers"]["round_timer"], {"status": "completed", "remaining_ms": 0})

    def test_shell_suspends_running_timer_and_invalidates_queued_events(self):
        rt = self.runtime()
        self.press(rt, "start", 0)
        token = rt.event_token()
        rt.enter_shell(3000)
        self.assertEqual(rt.press("tap", 20000, rt.event_token()), "ignored")
        rt.exit_shell(30000)
        self.assertEqual(rt.snapshot()["timers"]["round_timer"]["remaining_ms"], 7000)
        self.assertEqual(rt.press("tap", 30001, token), "ignored")
        rt.advance(36999)
        self.assertEqual(rt.screen, "play")
        rt.advance(37000)
        self.assertEqual(rt.screen, "result")

    def test_pause_resume_and_shell_preserve_paused_status(self):
        rt = self.runtime(fixture("focus-timer"))
        self.press(rt, "begin", 0)
        self.press(rt, "begin", 1000)  # Starting a running timer must not reset its deadline.
        self.press(rt, "pause", 2000)
        rt.enter_shell(3000)
        rt.exit_shell(50000)
        self.assertEqual(rt.snapshot()["timers"]["focus_timer"], {"status": "paused", "remaining_ms": 3000})
        self.press(rt, "begin", 50000)
        rt.advance(53000)
        self.assertEqual((rt.screen, rt.state["done"]), ("finished", True))

    def test_completed_start_noop_requires_reset(self):
        app = fixture("focus-timer")
        widget(app, "focus_timer")["on_complete"] = [{"type": "set", "state_key": "done", "value": True}]
        widget(app, "reset")["on_press"].append({"type": "navigate", "screen_id": "finished"})
        rt = self.runtime(app)
        self.press(rt, "begin", 0)
        rt.advance(5000)
        self.press(rt, "begin", 5001)
        self.assertEqual(rt.timers["focus_timer"]["status"], "completed")
        self.press(rt, "pause", 5002)
        self.assertEqual(rt.timers["focus_timer"]["status"], "completed")
        self.press(rt, "reset", 5003)
        self.assertEqual(rt.snapshot()["timers"]["focus_timer"], {"status": "idle", "remaining_ms": 5000})

    def test_navigation_does_not_pause_timer(self):
        app = fixture()
        widget(app, "tap")["on_press"] = [{"type": "navigate", "screen_id": "ready"}]
        rt = self.runtime(app)
        self.press(rt, "start", 0)
        self.press(rt, "tap", 1000)
        self.assertEqual(rt.screen, "ready")
        rt.advance(10000)
        self.assertEqual(rt.screen, "result")

    def test_overflow_rolls_back_state_timer_and_navigation(self):
        app = fixture()
        app["state"].update(score=INT_MAX, flag=False)
        widget(app, "start")["on_press"] = [
            {"type": "toggle", "state_key": "flag"},
            {"type": "timer_start", "widget_id": "round_timer"},
            {"type": "navigate", "screen_id": "play"},
            {"type": "increment", "state_key": "score", "amount": 1},
        ]
        rt = self.runtime(app)
        before = rt.snapshot()
        self.assertEqual(self.press(rt, "start", 0), "rejected")
        self.assertEqual(rt.snapshot(), before)
        self.assertEqual(len(rt.errors), 1)

    def test_completion_overflow_rolls_back_handler_but_fires_once(self):
        app = fixture()
        widget(app, "round_timer")["on_complete"] = [
            {"type": "navigate", "screen_id": "result"},
            {"type": "set", "state_key": "score", "value": INT_MAX},
            {"type": "increment", "state_key": "score", "amount": 1},
        ]
        rt = self.runtime(app)
        self.press(rt, "start", 0)
        rt.advance(10000)
        self.assertEqual((rt.screen, rt.state["score"]), ("play", 0))
        self.assertEqual(rt.timers["round_timer"]["status"], "completed")
        rt.advance(20000)
        self.assertEqual(len(rt.errors), 1)

    def test_simultaneous_timers_use_widget_id_order(self):
        app = fixture()
        app["screens"] = [{"id": "ready", "title": "Timers", "widgets": [
            {"id": "b_timer", "type": "timer", "duration_seconds": 1, "on_complete": [{"type": "increment", "state_key": "score", "amount": 2}]},
            {"id": "a_timer", "type": "timer", "duration_seconds": 1, "on_complete": [{"type": "set", "state_key": "score", "value": 1}]},
            {"id": "start", "type": "button", "text": "Start", "on_press": [{"type": "timer_start", "widget_id": "b_timer"}, {"type": "timer_start", "widget_id": "a_timer"}]}
        ]}]
        rt = self.runtime(app)
        self.press(rt, "start", 0)
        rt.advance(1000)
        self.assertEqual(rt.state["score"], 3)

    def test_install_preserves_previous_on_invalid_and_invalidates_old_tokens(self):
        rt = self.runtime()
        self.press(rt, "start", 0)
        self.press(rt, "tap", 1)
        token = rt.event_token()
        before = rt.snapshot()
        with self.assertRaises(ValidationError):
            rt.install(b"{}", 2)
        self.assertEqual(rt.snapshot(), before)
        rt.install(encode(fixture()), 2)
        self.press(rt, "start", 3)
        self.assertEqual(rt.press("tap", 4, token), "ignored")
        self.assertEqual(rt.state["score"], 0)

    def test_only_visible_actionable_widgets_accept_events(self):
        rt = self.runtime()
        for name in ("tap", "intro", "missing"):
            self.assertEqual(self.press(rt, name, 0), "ignored")
        self.assertEqual(rt.state["score"], 0)

    def test_clock_is_monotonic_and_rejects_booleans(self):
        rt = self.runtime()
        rt.advance(10)
        for invalid in (9, True, 10.1):
            with self.assertRaises(ValueError):
                rt.advance(invalid)
        self.assertEqual(rt.now_ms, 10)

    def test_fixture_scenarios_and_wrong_expectation_fail(self):
        for name in ("tap-sprint", "focus-timer"):
            raw = (SCENARIOS / (name + ".json")).read_bytes()
            result = run_scenario(self.runtime(fixture(name)), raw)
            self.assertTrue(result["passed"])
            altered = json.loads(raw)
            altered["steps"][-1]["expect"]["screen"] = "impossible"
            with self.assertRaises(AssertionError):
                run_scenario(self.runtime(fixture(name)), encode(altered))

    def test_empty_nested_expectation_asserts_actual_emptiness(self):
        scenario = {"scenario_version": 1, "steps": [{"op": "advance", "at_ms": 0,
                                                      "expect": {"state": {}}}]}
        with self.assertRaises(AssertionError):
            run_scenario(self.runtime(), encode(scenario))
        app = fixture()
        app["state"] = {}
        app["screens"] = [{"id": "ready", "title": "Empty state", "widgets": []}]
        self.assertTrue(run_scenario(self.runtime(app), encode(scenario))["passed"])

    def test_cli_reports_hash_and_scenario_without_hardware_claim(self):
        result = subprocess.run([sys.executable, "-m", "runtime.check", str(FIXTURES / "tap-sprint.json"),
                                 "--scenario", str(SCENARIOS / "tap-sprint.json")], cwd=str(ROOT),
                                capture_output=True, text=True, check=True)
        report = json.loads(result.stdout)
        self.assertTrue(report["scenario"]["passed"])
        self.assertEqual(report["evidence"], "host_validation_only")


if __name__ == "__main__":
    unittest.main()
