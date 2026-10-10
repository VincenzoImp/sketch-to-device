"""Fixed live comparison orchestration with synthetic providers and real runtime checks."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import compare_generation as comparison
from backend.providers import ProviderError
from runtime.validation import parse_app

ROOT = Path(__file__).absolute().parent.parent
SECRET = "synthetic-private-provider-detail"


def app():
    value = json.loads((ROOT / "agent-sdk/examples/colors.json").read_text())
    for screen, color in zip(value["screens"], comparison.COLORS):
        screen["widgets"][0].update(text="Hello World", background_color=color)
    return value


def encoded(value):
    return json.dumps(value).encode()


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.private = Path(self.temp.name) / "private"
        self.provider = self.private / "provider"
        self.provider.mkdir(parents=True)
        self.events = []
        self.calls = []

    def record(self, report, index, model, trace=True):
        run_id = str(index) * 32
        report.update(profile={"model": model}, timing={"run_id": run_id, "phase_ms": {
            "managed_generation": 123, "cleanup": 4, "host_checks": SECRET,
            SECRET: 321}, "private": SECRET})
        for name in (["managed-last-timing.json", "managed-last-execution.json"] if trace
                     else ["managed-last-timing.json"]):
            (self.provider / name).write_text(json.dumps({"run_id": run_id, "private": SECRET, "case": index}))

    def run_compare(self, generator, seconds=600):
        return comparison.compare(self.private, generator, seconds, self.events.append)

    def test_no_flag_cli_imports_no_backend_and_makes_no_private_files(self):
        command = ("import runpy,sys; n=runpy.run_path(sys.argv[1]); "
                   "assert not any(k.startswith('backend') for k in sys.modules); "
                   "assert n['main']([])==0; "
                   "assert not any(k.startswith('backend') for k in sys.modules)")
        result = subprocess.run([sys.executable, "-B", "-c", command,
                                 str(ROOT / "scripts/compare_generation.py")],
                                cwd=self.temp.name, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"result": "live_not_requested"})
        self.assertFalse((self.private / "comparisons").exists())

    def test_fixed_order_profile_exact_artifacts_and_correlated_archives(self):
        raw = encoded(app())
        def generate(prompt, media, progress, **options):
            index = len(self.calls) + 1
            self.calls.append((prompt, media, {k: v for k, v in options.items() if k != "report"}))
            self.record(options["report"], index, options["model"])
            progress("generating", SECRET)
            progress(SECRET, SECRET)
            return raw
        result, run = self.run_compare(generate)
        self.assertEqual(self.calls, [(comparison.PROMPT, [], {"model": model, "token_budget": 200000,
                                                               "job_seconds": 600}) for model in comparison.MODELS])
        self.assertTrue(all(item["fidelity_passed"] for item in result["cases"]))
        self.assertFalse(result["device_installed"])
        for index, item in enumerate(result["cases"], 1):
            case = run / str(index)
            self.assertEqual(item["sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual((case / "app.json").read_bytes(), raw)
            self.assertEqual(item["phase_ms"], {"managed_generation": 123, "cleanup": 4})
            self.assertTrue(item["trace_archived"] and item["timing_archived"])
            for name in ("managed-last-timing.json", "managed-last-execution.json"):
                self.assertEqual(json.loads((case / name).read_text())["case"], index)
        self.assertEqual((run / "prompt.txt").read_text(), comparison.PROMPT)
        for path in run.rglob("*"):
            self.assertEqual(path.stat().st_mode & 0o777, 0o700 if path.is_dir() else 0o600)
        self.assertNotIn(SECRET, "".join(self.events))
        self.assertNotIn(comparison.PROMPT, "".join(self.events))

    def test_failed_second_call_does_not_archive_previous_trace_or_recommend_winner(self):
        def generate(_prompt, _media, _progress, **options):
            index = len(self.calls) + 1
            self.calls.append(options["model"])
            self.record(options["report"], index, options["model"], trace=index == 1)
            if index == 2:
                raise ProviderError("deadline", {"message": SECRET})
            return encoded(app())
        result, run = self.run_compare(generate, 180)
        self.assertTrue(result["cases"][0]["fidelity_passed"])
        failed = result["cases"][1]
        self.assertEqual(failed["code"], "deadline")
        self.assertFalse(failed["trace_archived"])
        self.assertTrue(failed["timing_archived"])
        self.assertFalse((run / "2/managed-last-execution.json").exists())
        self.assertNotIn("winner", result)
        self.assertNotIn(SECRET, json.dumps(result))
        self.assertEqual(failed["job_seconds"], 180)

    def test_valid_wrong_behavior_is_not_a_fidelity_pass(self):
        baseline = app()
        wrong_color = copy.deepcopy(baseline)
        wrong_color["screens"][1]["widgets"][0]["background_color"] = "#FF0000"
        wrong_label = copy.deepcopy(baseline)
        wrong_label["screens"][0]["widgets"][0]["text"] = "Hello world"
        extra = copy.deepcopy(baseline)
        button = copy.deepcopy(extra["screens"][0]["widgets"][0])
        button["id"] = "second_button"
        extra["screens"][0]["widgets"].append(button)
        for value in (wrong_color, wrong_label, extra):
            raw = encoded(value)
            parse_app(raw)
            self.assertFalse(comparison.fidelity(raw))
        result, run = self.run_compare(lambda *args, **kwargs: encoded(wrong_color))
        self.assertEqual([item["result"] for item in result["cases"]], ["fidelity_failed"] * 2)
        self.assertTrue((run / "1/app.json").exists())
        # The theme accent is a real rendered color even without an explicit override.
        themed = app()
        del themed["screens"][2]["widgets"][0]["background_color"]
        self.assertTrue(comparison.fidelity(encoded(themed)))

    def test_changed_context_stops_before_second_paid_call(self):
        with patch.object(comparison, "context_hash", side_effect=["a", "a", "a", "b", "b"]):
            def generate(*_args, **options):
                self.calls.append(options["model"])
                return encoded(app())
            result, _ = self.run_compare(generate)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(result["cases"][1]["result"], "context_changed")

    def test_one_color_cycle_then_stuck_does_not_pass_repeating_requirement(self):
        value = app()
        terminal = copy.deepcopy(value["screens"][0])
        terminal["id"] = "terminal_pink"
        terminal["widgets"][0]["id"] = "terminal_button"
        terminal["widgets"][0]["on_press"] = [{"type": "navigate", "screen_id": "terminal_pink"}]
        value["screens"][2]["widgets"][0]["on_press"] = [{"type": "navigate", "screen_id": "terminal_pink"}]
        value["screens"].append(terminal)
        raw = encoded(value)
        parse_app(raw)
        self.assertFalse(comparison.fidelity(raw))
        self.assertTrue(comparison.fidelity(encoded(app())))

    def test_unknown_exception_and_unmatched_run_files_stay_private(self):
        (self.provider / "managed-last-execution.json").write_text(json.dumps({"run_id": "f" * 32, "data": SECRET}))
        def fail(*_args, **options):
            options["report"].update(timing={"run_id": "1" * 32})
            raise RuntimeError(SECRET)
        result, _ = self.run_compare(fail)
        self.assertTrue(all(item["code"] == "generation" and not item["trace_archived"]
                            for item in result["cases"]))
        self.assertNotIn(SECRET, "".join(self.events))


if __name__ == "__main__":
    unittest.main()
