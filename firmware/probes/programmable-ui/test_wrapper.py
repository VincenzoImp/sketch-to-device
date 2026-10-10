"""Host wrapper boundary tests. No network, main firmware or hardware writes."""

import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("ui_probe_wrapper", ROOT / "scripts/probe_programmable_ui.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class WrapperTests(unittest.TestCase):
    def test_missing_dependency_status_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "untouched"
            with patch.object(probe, "BASE", target), \
                    patch.object(probe.engine, "status", return_value={"status": "dependency_absent"}):
                with self.assertRaisesRegex(probe.ProbeError, "quickjs_missing_use_engine_fetch"):
                    probe.status()
                self.assertFalse(target.exists())

    def test_actual_official_verifier_rejects_changed_component(self):
        if not probe.engine.IDF_PYTHON.is_file():
            self.skipTest("installed official verifier unavailable")
        with tempfile.TemporaryDirectory() as folder:
            fake = Path(folder)
            (fake / "idf_component.yml").write_text(
                "version: 9.4.0\nrepository_info:\n"
                "  commit_sha: c016f72d4c125098287be5e83c0f1abed4706ee5\n  path: .\n")
            with patch.object(probe, "LVGL", fake), \
                    patch.object(probe.engine, "status", return_value={"status": "dependency_verified"}):
                with self.assertRaisesRegex(probe.ProbeError, "lvgl_verification_failed"):
                    probe.status()

    def test_result_rejects_partial_runs_and_unexpected_output(self):
        good = {"status": "real_ui_probe_passed", "engine": "QuickJS-NG0.14.0", "lvgl": "9.4",
                "installs": 110, "callbacks": 142, "rejected_initializations": 22,
                "stale_events": 113, "dropped_events": 5, "remaining_apps": 0,
                "physical_execution": False, "peak_engine_allocation_payload": 106466}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "result.json"
            path.write_text(json.dumps(good))
            self.assertEqual(probe.checked_result(path), good)
            for changed in ({"callbacks": 1}, {"remaining_apps": False},
                            {"physical_execution": True}, {"raw_log": "synthetic-private"},
                            {"peak_engine_allocation_payload": 1000000}):
                path.write_text(json.dumps(dict(good, **changed)))
                with self.assertRaisesRegex(probe.ProbeError, "host_result_invalid"):
                    probe.checked_result(path)
            path.write_text("x" * 4097)
            with self.assertRaisesRegex(probe.ProbeError, "host_result_invalid"):
                probe.checked_result(path)

    def test_actual_child_output_is_private_and_failures_are_fixed(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(probe, "BASE", Path(folder)):
            path = probe.execute([sys.executable, "-c", "print('synthetic-private')"], "child.log", 2)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(path.read_text(), "synthetic-private\n")
            with self.assertRaisesRegex(probe.ProbeError, "^host_process_failed$"):
                probe.execute([sys.executable, "-c", "print('synthetic-private');raise SystemExit(2)"],
                              "failed.log", 2)

    def test_actual_sleeping_process_is_bounded(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(probe, "BASE", Path(folder)):
            started = time.monotonic()
            with self.assertRaisesRegex(probe.ProbeError, "^host_process_timeout$"):
                probe.execute([sys.executable, "-c", "import time;time.sleep(30)"], "timeout.log", 0.1)
            self.assertLess(time.monotonic() - started, 6)

    def test_symlink_log_is_not_followed(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(probe, "BASE", Path(folder)):
            base = Path(folder)
            (base / "outside").write_text("keep")
            (base / "child.log").symlink_to(base / "outside")
            with self.assertRaisesRegex(probe.ProbeError, "unsafe_output_path"):
                probe.execute([sys.executable, "-c", "pass"], "child.log", 1)
            self.assertEqual((base / "outside").read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
