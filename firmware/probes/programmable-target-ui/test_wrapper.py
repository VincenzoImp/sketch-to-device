"""Offline wrapper boundary checks, separate from a real target build."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import signal
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("target_probe", ROOT / "scripts/probe_programmable_target.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class WrapperTests(unittest.TestCase):
    def test_default_is_read_only_status_without_build(self):
        with patch.object(probe, "status", return_value={"status": "dependencies_verified"}) as status, \
                patch.object(probe, "build") as build, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(probe.main([]), 0)
        status.assert_called_once_with()
        build.assert_not_called()
        self.assertEqual(json.loads(output.getvalue()), {"status": "dependencies_verified"})

    def test_missing_dependencies_prevent_build_and_hide_external_details(self):
        with patch.object(probe, "status", side_effect=OSError("PRIVATE")), \
                patch.object(probe.subprocess, "Popen") as process, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(probe.main(["--build"]), 1)
        process.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())["error_code"], "local_io_failed")
        self.assertNotIn("PRIVATE", output.getvalue())

    def test_unsafe_output_link_is_rejected_before_process(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary) / "probe"
            base.symlink_to(Path(temporary), target_is_directory=True)
            with patch.object(probe, "BASE", base), patch.object(probe, "status"), \
                    patch.object(probe.subprocess, "Popen") as process, self.assertRaises(probe.ui.ProbeError):
                probe.build()
            process.assert_not_called()

    def test_timeout_stops_process_group_and_keeps_log_private(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary) / "probe"
            process = Mock(pid=123)
            process.wait.side_effect = [subprocess.TimeoutExpired("build", 420), 0]
            with patch.object(probe, "BASE", base), patch.object(probe, "status"), \
                    patch.object(probe.subprocess, "Popen", return_value=process) as launch, \
                    patch.object(probe.os, "killpg") as kill, self.assertRaises(probe.ui.ProbeError) as caught:
                probe.build()
            self.assertEqual(str(caught.exception), "target_build_timeout")
            kill.assert_called_once_with(123, signal.SIGTERM)
            self.assertTrue(launch.call_args.kwargs["start_new_session"])
            self.assertEqual(launch.call_args.kwargs["umask"], 0o077)
            self.assertEqual((base / "build.log").stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
