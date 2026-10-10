"""Actual subprocess/frame and Python/C wire parity checks; no providers/device."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from runtime.program import validate_program
from runtime.validation import ValidationError

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / ".tools/program-core-host/program_runner"


def package(source="gfx.begin('#ff69b4');gfx.end();"):
    return dict(schema_version=2, app_id="native_test", name="Native test", version=1,
                runtime="quickjs-ng-0.14.0", sdk="device-js-1", profile="p4-canvas-1",
                requires=["canvas", "input", "time"], source=source, assets=[])


def scenario(events=None):
    return dict(version=1, seed=123, initial_time_ms=0, wall_time=None,
                events=events if events is not None else [dict(type="frame", name="initial")])


class RunnerTests(unittest.TestCase):
    def run_actual(self, value, events=None):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            raw = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode()
            (folder / "package.json").write_bytes(raw)
            event_bytes = events if isinstance(events, bytes) else json.dumps(events or scenario()).encode()
            (folder / "scenario.json").write_bytes(event_bytes)
            result = subprocess.run([str(RUNNER), "--package", str(folder / "package.json"),
                                     "--scenario", str(folder / "scenario.json"),
                                     "--output", str(folder)], capture_output=True, timeout=10)
            self.assertNotIn(b"Sanitizer", result.stderr)
            self.assertIn(result.returncode, (0, 1))
            report = json.loads(result.stdout)
            files = {f.name: f.read_bytes() for f in folder.glob("frame-*")}
            return report, files

    def test_actual_frames_and_computed_pointer_logic(self):
        app = package("let n=0;const colors=['#ff69b4','#4287f5','#80ff80'];"
                      "function draw(){gfx.begin(colors[n%3]);gfx.end()}draw();"
                      "app.onPointer(e=>{if(e.type==='up'){n++;draw()}})")
        events = [dict(type="frame", name="initial")]
        for i in range(1, 4):
            events.extend([dict(type="pointer", phase="up", x=12, y=24, time_ms=i),
                           dict(type="frame", name="step_" + str(i))])
        report, files = self.run_actual(app, scenario(events))
        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["callbacks"], 3)
        hashes = [f["sha256"] for f in report["frames"]]
        self.assertEqual(hashes[0], hashes[3])
        self.assertEqual(len(set(hashes[:3])), 3)
        for frame in report["frames"]:
            raw = files[frame["rgb565"]]
            self.assertEqual(len(raw), 320 * 432 * 2)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), frame["sha256"])
            self.assertTrue(files[frame["ppm"]].startswith(b"P6\n320 432\n255\n"))

    def test_wire_parity_and_exact_asset_hash(self):
        app = package("gfx.begin('#000000');gfx.image('pixel',0,0);gfx.end()")
        pixels = bytes([255, 0, 0, 255])
        app["assets"] = [dict(id="pixel", width=1, height=1, format="rgba8888",
                              sha256=hashlib.sha256(pixels).hexdigest(),
                              data_b64=base64.b64encode(pixels).decode())]
        raw = json.dumps(app).encode()
        validate_program(raw)
        report, files = self.run_actual(raw)
        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["package_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(files[report["frames"][0]["rgb565"]][:2], b"\x00\xf8")
        variants = [raw.replace(b'"width": 1', b'"width": 1.0'),
                    raw.replace(b'"version": 1', b'"version": true'),
                    raw.replace(b'"version": 1', b'"version": 1e0'),
                    raw.replace(b'"version": 1', b'"version": 1,"version": 2'),
                    raw.replace(b'"source":', b'"extra": 0,"source":'),
                    raw.replace(b'"rgba8888"', b'"rgb565"'),
                    raw.replace(b'/wAA/w==', b'/wAA/x=='),
                    raw.replace(app["assets"][0]["sha256"].encode(), b"0" * 64),
                    raw.replace(b'"name": "Native test"', b'"name": "\\u0000test"'),
                    raw.replace(b'"name": "Native test"', b'"name": "\\ud800"'),
                    raw.replace(b'"name": "Native test"', b'"name": "\xff"'),
                    raw.replace(b'"version": 1', b'"version": 2147483648'),
                    raw + b" null", b"\xef\xbb\xbf" + raw, b"\x0b" + raw]
        for invalid in variants:
            with self.subTest(raw=invalid[:30]):
                with self.assertRaises(ValidationError):
                    validate_program(invalid)
                result, _ = self.run_actual(invalid)
                self.assertEqual(result["status"], "rejected")
                self.assertEqual(result["error"], "invalid_package")

    def test_failed_callback_keeps_last_frame_and_fails_process(self):
        app = package("gfx.begin('#123456');gfx.end();app.onTick(async()=>{"
                      "gfx.begin('#ffffff');gfx.end();throw Error('failed')})")
        events = scenario([dict(type="frame", name="before"), dict(type="tick", time_ms=50)])
        report, _ = self.run_actual(app, events)
        self.assertEqual(report["status"], "rejected")
        self.assertEqual(report["error"], "unhandled_rejection")
        self.assertEqual(report["committed_frames"], 1)
        self.assertEqual(len(report["frames"]), 1)

    def test_explicit_wall_clock_quality(self):
        for source, expected_epoch, valid in (("unavailable", None, False),
                                               ("estimated", 123456, False),
                                               ("synchronized", 123456, True)):
            with self.subTest(source=source):
                event_input = scenario()
                if source != "unavailable":
                    event_input["wall_time"] = dict(epoch_ms=123456, source=source)
                expected = json.dumps(dict(epochMs=expected_epoch, valid=valid, source=source))
                app = package("const actual=app.wallTime(),expected=" + expected + ";"
                              "for(const k of Object.keys(expected)){"
                              "if(actual[k]!==expected[k])throw Error('clock quality')}"
                              "gfx.begin('#000000');gfx.end()")
                report, _ = self.run_actual(app, event_input)
                self.assertEqual(report["status"], "completed")

    def test_rejects_scenario_path_escape_backwards_time_and_overflow(self):
        cases = [scenario([dict(type="frame", name="../escape")]),
                 scenario([dict(type="tick", time_ms=5), dict(type="tick", time_ms=4)]),
                 scenario([dict(type="tick", time_ms=120001)]),
                 scenario([dict(type="pointer", phase="up", x=320, y=0, time_ms=1)]),
                 scenario([dict(type="frame", name="same"), dict(type="frame", name="same")]),
                 scenario([dict(type="tick", time_ms=0)] * 4097)]
        valid_bytes = json.dumps(scenario()).encode()
        cases.append(valid_bytes + b" " * (524289 - len(valid_bytes)))
        for case in cases:
            result, frames = self.run_actual(package(), case)
            self.assertEqual(result["error"], "invalid_scenario")
            self.assertFalse(frames)


if __name__ == "__main__":
    unittest.main()
