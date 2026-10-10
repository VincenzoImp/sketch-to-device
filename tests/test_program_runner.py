"""Real native process/frame tests plus process-supervision failure checks."""

import hashlib
from pathlib import Path
import struct
import tempfile
import time
import unittest
from unittest.mock import patch
import zlib

from backend.program_runner import RunnerError, execute_program, scenario_bytes
from runtime.program import assemble_program
from runtime.validation import ValidationError


def package(source):
    return assemble_program(app_id="runner_test", name="Runner test", version=1,
                            source=source, assets=[], requires=["canvas", "input", "time"])


def scenario(events):
    return dict(version=1, seed=123, initial_time_ms=0, wall_time=None, events=events)


def rgb_from_png(raw):
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("PNG signature")
    cursor, compressed = 8, bytearray()
    while cursor < len(raw):
        size = struct.unpack(">I", raw[cursor:cursor + 4])[0]
        kind = raw[cursor + 4:cursor + 8]
        data = raw[cursor + 8:cursor + 8 + size]
        crc = struct.unpack(">I", raw[cursor + 8 + size:cursor + 12 + size])[0]
        if zlib.crc32(kind + data) != crc:
            raise ValueError("PNG CRC")
        if kind == b"IDAT":
            compressed.extend(data)
        cursor += 12 + size
    return zlib.decompress(compressed)


class ProgramRunnerTests(unittest.TestCase):
    def test_actual_input_frames_exact_identity_and_deterministic_reexecution(self):
        raw = package("let color='#ff0000';function draw(){gfx.begin(color);gfx.end()}draw();"
                      "app.onPointer(e=>{if(e.type==='up'){color='#00ff00';draw()}})")
        steps = scenario([dict(type="frame", name="before"),
                          dict(type="pointer", phase="up", x=160, y=216, time_ms=40),
                          dict(type="frame", name="after")])
        first = execute_program(raw, steps, deadline=time.monotonic() + 10)
        second = execute_program(raw, steps, deadline=time.monotonic() + 10)
        self.assertTrue(first.succeeded)
        self.assertEqual(first.report["package_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(first.report["scenario_sha256"], hashlib.sha256(first.scenario).hexdigest())
        self.assertEqual(first.report, second.report)
        self.assertEqual(first.images, second.images)
        red = rgb_from_png(first.images[0][1])
        green = rgb_from_png(first.images[1][1])
        self.assertEqual(red[:7], b"\0\xff\0\0\xff\0\0")
        self.assertEqual(green[:7], b"\0\0\xff\0\0\xff\0")
        self.assertFalse(first.report["physical_execution"])

    def test_runtime_failures_are_failed_results_with_prior_frames(self):
        cases = [("throw Error('controlled');", "script_exception"),
                 ("while(true){}", "execution_budget"),
                 ("Promise.reject(Error('controlled'))", "unhandled_rejection")]
        for callback, error in cases:
            with self.subTest(callback=callback):
                result = execute_program(package("gfx.begin('#112233');gfx.end();app.onTick(()=>{" + callback + "})"),
                                         scenario([dict(type="frame", name="before"), dict(type="tick", time_ms=30)]),
                                         deadline=time.monotonic() + 10)
                self.assertFalse(result.succeeded)
                self.assertEqual(result.report["error"], error)
                self.assertEqual([name for name, _ in result.images], ["before"])

    def test_invalid_scenarios_rejected_before_process(self):
        cases = [scenario([dict(type="frame", name="../escape")]),
                 scenario([dict(type="tick", time_ms=2), dict(type="tick", time_ms=1)]),
                 scenario([dict(type="pointer", phase="up", x=True, y=0, time_ms=0)]),
                 scenario([dict(type="frame", name="same")] * 2)]
        for value in cases:
            with self.assertRaises(ValidationError):
                execute_program(package("1"), value, deadline=time.monotonic() + 2,
                                runner=Path("/nonexistent/should-not-be-opened"))

    def test_process_deadline_kills_process_group_and_reaps(self):
        with tempfile.TemporaryDirectory() as temporary:
            runner = Path(temporary) / "slow"
            runner.write_text("#!/bin/sh\nsleep 20 &\nwait\n")
            runner.chmod(0o700)
            started = time.monotonic()
            with self.assertRaisesRegex(RunnerError, "runner_timeout"):
                execute_program(package("1"), scenario([]), deadline=started + 0.15, runner=runner)
            self.assertLess(time.monotonic() - started, 2)

    def test_unexpected_process_output_cannot_certify_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            runner = Path(temporary) / "bad"
            runner.write_text("#!/bin/sh\nprintf '%s' '{\"status\":\"completed\"}'\n")
            runner.chmod(0o700)
            with self.assertRaisesRegex(RunnerError, "runner_identity_mismatch"):
                execute_program(package("1"), scenario([]), deadline=time.monotonic() + 2, runner=runner)

    def test_deadline_expiring_during_actual_frame_verification_cannot_pass(self):
        from backend import program_runner
        encode = program_runner.png_from_rgb
        def slower_encoding(rgb):
            time.sleep(0.35)
            return encode(rgb)
        with patch.object(program_runner, "png_from_rgb", slower_encoding):
            with self.assertRaisesRegex(RunnerError, "runner_timeout"):
                execute_program(package("gfx.begin('#112233');gfx.end();"),
                                scenario([dict(type="frame", name="initial")]),
                                deadline=time.monotonic() + 0.3)


if __name__ == "__main__":
    unittest.main()
