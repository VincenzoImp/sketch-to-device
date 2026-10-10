"""Execute exact program bytes through the shared native runtime.

The executable is trusted platform code. Generated source only reaches its
controlled interpreter, never command arguments or the host environment.
This is process supervision, not an OS sandbox or physical execution proof.
"""

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import struct
import subprocess
import tempfile
import time
import zlib

from runtime.program import (IDENTIFIER, LIMITS, PROFILE, _integer, _object,
                             decode, fail, program_report)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNNER = ROOT / ".tools/program-core-host/program_runner"
MAX_CLOCK = 2 ** 53 - 1 - LIMITS["scenario_duration_ms"]
WIDTH, HEIGHT = 320, 432
PPM_HEADER = b"P6\n320 432\n255\n"


class RunnerError(ValueError):
    """Fixed diagnostic, safe to return without paths or process output."""


def _diagnostic(value):
    """Validate bounded app-origin repair hints; they never establish success."""
    if (type(value) is not dict or set(value) != {
            "phase", "exception_name", "message", "line", "column", "truncated"}
            or type(value["phase"]) is not str or value["phase"] not in {"initialization", "tick", "pointer"}
            or type(value["truncated"]) is not bool):
        raise RunnerError("runner_output_invalid")
    for name, maximum in (("exception_name", 48), ("message", 192)):
        text = value[name]
        if type(text) is not str or len(text) > maximum or any(not 32 <= ord(c) <= 126 for c in text):
            raise RunnerError("runner_output_invalid")
    for name in ("line", "column"):
        if value[name] is not None and (type(value[name]) is not int or not 1 <= value[name] <= 65536):
            raise RunnerError("runner_output_invalid")
    return dict(value)


def scenario_bytes(value):
    """Strict independent validation before starting an executable."""
    _object(value, {"version", "seed", "initial_time_ms", "wall_time", "events"}, "$.scenario")
    _integer(value["version"], 1, 1, "$.scenario.version")
    _integer(value["seed"], 0, 2 ** 32 - 1, "$.scenario.seed")
    start = value["initial_time_ms"]
    _integer(start, 0, MAX_CLOCK, "$.scenario.initial_time_ms")
    wall = value["wall_time"]
    if wall is not None:
        _object(wall, {"epoch_ms", "source"}, "$.scenario.wall_time")
        _integer(wall["epoch_ms"], 0, MAX_CLOCK, "$.scenario.wall_time.epoch_ms")
        if wall["source"] not in ("estimated", "synchronized"):
            fail("clock", "$.scenario.wall_time.source", "Unknown clock quality")
    events = value["events"]
    if type(events) is not list or len(events) > LIMITS["scenario_events"]:
        fail("events", "$.scenario.events", "Too many scenario events")
    names, last = set(), start
    for event in events:
        if type(event) is not dict or type(event.get("type")) is not str:
            fail("event", "$.scenario.events", "Expected an event object")
        kind = event["type"]
        if kind == "frame":
            _object(event, {"type", "name"}, "$.scenario.frame")
            name = event["name"]
            if (type(name) is not str or not IDENTIFIER.fullmatch(name)
                    or name in names or len(names) >= LIMITS["scenario_frames"]):
                fail("frame", "$.scenario.frame.name", "Expected a unique bounded frame name")
            names.add(name)
            continue
        fields = {"type", "time_ms"}
        if kind == "pointer":
            fields.update(("phase", "x", "y"))
            if event.get("phase") not in ("down", "move", "up", "cancel"):
                fail("pointer", "$.scenario.pointer", "Unknown pointer phase")
            _integer(event.get("x"), 0, WIDTH - 1, "$.scenario.pointer.x")
            _integer(event.get("y"), 0, HEIGHT - 1, "$.scenario.pointer.y")
        elif kind not in ("tick", "pause", "resume"):
            fail("event", "$.scenario.events", "Unknown event type")
        _object(event, fields, "$.scenario.event")
        _integer(event["time_ms"], last, start + LIMITS["scenario_duration_ms"], "$.scenario.event.time_ms")
        last = event["time_ms"]
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    if len(raw) > LIMITS["scenario_bytes"]:
        fail("bytes", "$.scenario", "Scenario exceeds the byte limit")
    return raw


def _read(path, maximum):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
            raise RunnerError("runner_output_invalid")
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise RunnerError("runner_output_invalid")
    return raw


def png_from_rgb(rgb):
    """Lossless PNG encoding of verified native pixels, without imaging tools."""
    if len(rgb) != WIDTH * HEIGHT * 3:
        raise RunnerError("runner_frame_invalid")
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    rows = b"".join(b"\0" + rgb[offset:offset + WIDTH * 3]
                    for offset in range(0, len(rgb), WIDTH * 3))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


@dataclass
class RunResult:
    report: dict
    runner_sha256: str
    scenario: bytes
    images: list  # (frame name, lossless PNG bytes); separate from durable receipt JSON

    @property
    def succeeded(self):
        return self.report.get("status") == "completed"


def execute_program(package, scenario, *, deadline, runner=DEFAULT_RUNNER):
    """Run with a bounded process lifetime; inputs are immutable serialized bytes.

    runner is trusted deployment configuration, never an agent/tool argument.
    The copied executable's hash identifies exactly the checker used.
    """
    deadline = min(deadline, time.monotonic() + 30)
    def check_deadline():
        if deadline <= time.monotonic():
            raise RunnerError("runner_timeout")
    check_deadline()
    manifest = program_report(package)
    scenario_raw = scenario_bytes(scenario)
    executable = _read(runner, 64 * 1024 * 1024)
    runner_hash = hashlib.sha256(executable).hexdigest()
    check_deadline()
    with tempfile.TemporaryDirectory(prefix="program-run-") as temporary:
        folder = Path(temporary)
        for name, raw in (("package.json", package), ("scenario.json", scenario_raw), ("runner", executable)):
            path = folder / name
            path.write_bytes(raw)
            path.chmod(0o700 if name == "runner" else 0o600)
        with (folder / "stdout").open("wb") as stdout, (folder / "stderr").open("wb") as stderr:
            check_deadline()
            process = subprocess.Popen([str(folder / "runner"), "--package", str(folder / "package.json"),
                                        "--scenario", str(folder / "scenario.json"), "--output", str(folder)],
                                       cwd=folder, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                       env={"PATH": "/usr/bin:/bin", "LC_ALL": "C", "TMPDIR": str(folder)},
                                       start_new_session=True)
            try:
                process.wait(timeout=max(0.001, deadline - time.monotonic()))
            except BaseException as exc:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)
                if isinstance(exc, subprocess.TimeoutExpired):
                    raise RunnerError("runner_timeout") from None
                raise
        check_deadline()
        # A sanitizer crash or unexpected stderr never becomes a passing receipt.
        if process.returncode not in (0, 1) or _read(folder / "stderr", 65536):
            raise RunnerError("runner_process_failed")
        report = decode(_read(folder / "stdout", 65536))
        if not isinstance(report, dict):
            raise RunnerError("runner_output_invalid")
        expected_status = "completed" if process.returncode == 0 else "rejected"
        if (report.get("status") != expected_status or report.get("package_sha256") != manifest["sha256"]
                or report.get("engine") != PROFILE["engine"] or report.get("sdk") != PROFILE["sdk"]
                or report.get("profile") != PROFILE["profile"] or report.get("physical_execution") is not False):
            raise RunnerError("runner_identity_mismatch")
        steps = report.get("steps")
        if type(steps) is not int or not 0 <= steps <= len(scenario["events"]):
            raise RunnerError("runner_output_invalid")
        if process.returncode == 0 and steps != len(scenario["events"]):
            raise RunnerError("runner_incomplete")
        if process.returncode == 1 and (type(report.get("error")) is not str
                                       or not IDENTIFIER.fullmatch(report["error"])):
            raise RunnerError("runner_output_invalid")
        if "diagnostic" in report:
            if process.returncode != 1:
                raise RunnerError("runner_output_invalid")
            report["diagnostic"] = _diagnostic(report["diagnostic"])
        expected_names = [e["name"] for e in scenario["events"][:steps] if e["type"] == "frame"]
        frames = report.get("frames")
        if type(frames) is not list or len(frames) > len(expected_names):
            raise RunnerError("runner_frame_invalid")
        if process.returncode == 0 and len(frames) != len(expected_names):
            raise RunnerError("runner_incomplete")
        images = []
        for index, frame in enumerate(frames):
            check_deadline()
            if (type(frame) is not dict or frame.get("name") != expected_names[index]
                    or frame.get("width") != WIDTH or frame.get("height") != HEIGHT
                    or frame.get("rgb565") != "frame-{:04d}.rgb565".format(index)
                    or frame.get("ppm") != "frame-{:04d}.ppm".format(index)):
                raise RunnerError("runner_frame_invalid")
            pixels = _read(folder / frame["rgb565"], WIDTH * HEIGHT * 2)
            ppm = _read(folder / frame["ppm"], len(PPM_HEADER) + WIDTH * HEIGHT * 3)
            if (len(pixels) != WIDTH * HEIGHT * 2 or hashlib.sha256(pixels).hexdigest() != frame.get("sha256")
                    or not ppm.startswith(PPM_HEADER) or len(ppm) != len(PPM_HEADER) + WIDTH * HEIGHT * 3):
                raise RunnerError("runner_frame_invalid")
            rgb = bytearray()
            for (pixel,) in struct.iter_unpack("<H", pixels):
                rgb.extend(((pixel >> 11) * 255 // 31, ((pixel >> 5) & 63) * 255 // 63, (pixel & 31) * 255 // 31))
            if bytes(rgb) != ppm[len(PPM_HEADER):]:
                raise RunnerError("runner_frame_invalid")
            png = png_from_rgb(rgb)
            frame["png_sha256"] = hashlib.sha256(png).hexdigest()
            images.append((frame["name"], png))
            check_deadline()
        report["scenario_sha256"] = hashlib.sha256(scenario_raw).hexdigest()
        report["runner_sha256"] = runner_hash
        check_deadline()
        return RunResult(report, runner_hash, scenario_raw, images)
