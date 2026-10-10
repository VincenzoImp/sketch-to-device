#!/usr/bin/env python3
"""Prove fresh managed JavaScript authorship, asset tools and actual execution.

Uses an isolated private job/database and a synthetic reference image. It never
publishes a deployment, touches the current service or communicates with a board.
"""

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct
import sys
import time
import uuid
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.program_agent import run_program_agent, _write
from backend.program_broker import ProgramBroker, tool_definitions
from backend.program_runner import execute_program
from backend.program_store import ProgramStore
from backend.providers import ProviderError
from runtime.program import assemble_program, asset_bytes

PROMPT = """Write an original JavaScript application named Reference Switch.
Use the original uploaded image identified by 'reference' as a 24x24 image at
x=20,y=100, preserving its colored pattern exactly; use the asset preparation tool and
gfx.image, not a replacement colored rectangle. Start with a fully red
#FF0000 background. Each pointer release anywhere cycles the whole background
green #00FF00, blue #0000FF, then red #FF0000. Preserve the uploaded image in
every frame. Keep the outermost bottom-right pixel as background, with no border.
Draw only the background and uploaded image; the package name is Reference Switch.
Use ordinary authored code, consult the SDK, run meaningful interaction tests
and inspect actual screenshots before submitting a successful receipt.
This is a diagnostic of generated source and asset reuse, not a physical test.
"""


def scenario():
    events = [{"type": "frame", "name": "initial"}]
    for index, (x, y) in enumerate(((0, 0), (319, 431), (30, 110), (160, 216), (319, 0), (0, 431)), 1):
        events.extend([{"type": "pointer", "phase": "down", "x": x, "y": y, "time_ms": index * 100},
                       {"type": "pointer", "phase": "up", "x": x, "y": y, "time_ms": index * 100 + 30},
                       {"type": "frame", "name": "press_" + str(index)}])
    return {"version": 1, "seed": 456, "initial_time_ms": 0, "wall_time": None, "events": events}


def pixels(png):
    """Read fixed lossless PNGs returned by the trusted runner wrapper only."""
    offset, encoded = 8, bytearray()
    if png[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("unexpected_frame")
    while offset < len(png):
        size = struct.unpack(">I", png[offset:offset + 4])[0]
        if png[offset + 4:offset + 8] == b"IDAT":
            encoded.extend(png[offset + 8:offset + 8 + size])
        offset += size + 12
    raw = zlib.decompress(encoded)
    if len(raw) != 432 * (320 * 3 + 1) or any(raw[row * 961] for row in range(432)):
        raise ValueError("unexpected_frame")
    return b"".join(raw[y * 961 + 1:(y + 1) * 961] for y in range(432))


def reference_rgb():
    colors = ((255, 255, 0), (255, 0, 255), (0, 255, 255), (255, 255, 255))
    return bytes(channel for y in range(24) for x in range(24)
                 for channel in colors[(x // 6 + y // 6) % 4])


def original_png():
    rgb = reference_rgb()
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    rows = b"".join(b"\0" + rgb[y * 72:(y + 1) * 72] for y in range(24))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 24, 24, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def verify_generated(body, result, expected_asset=None):
    app = json.loads(body)
    if not result.succeeded or len(result.images) != 7 or app["name"] != "Reference Switch" or not app["assets"]:
        return False
    rgb = reference_rgb() if expected_asset is None else expected_asset
    expected = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    for index, (_, png) in enumerate(result.images):
        frame = bytearray(bytes(expected[index % 3]) * 320 * 432)
        for y in range(24):
            at = ((100 + y) * 320 + 20) * 3
            frame[at:at + 72] = rgb[y * 72:(y + 1) * 72]
        if pixels(png) != frame:
            return False
    return True


def check_asset_dependence(body):
    """A separate host-only mutation proves rendering reads the packaged image.

    Never selected or published; source/app_id/name/version are preserved.
    Changed asset bytes and hash form a distinct host-only package.
    """
    app = json.loads(body)
    expected = reference_rgb()
    expected_rgba = b"".join(expected[i:i + 3] + b"\xff" for i in range(0, len(expected), 3))
    matching = [asset for asset in app["assets"] if asset["width"] == asset["height"] == 24
                and asset_bytes(asset) == expected_rgba]
    if len(matching) != 1:
        return False
    changed = bytes([0, 0, 0, 255]) * 24 * 24
    matching[0].update(data_b64=base64.b64encode(changed).decode(), sha256=hashlib.sha256(changed).hexdigest())
    altered = assemble_program(**{key: app[key] for key in ("app_id", "name", "version", "source", "assets", "requires")})
    result = execute_program(altered, scenario(), deadline=time.monotonic() + 20)
    return verify_generated(altered, result, bytes(24 * 24 * 3))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args(argv)
    if not args.live:
        print(json.dumps({"status": "ready_for_live_probe", "device_installed": False}))
        return 0
    started = time.monotonic()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
    folder = ROOT / "private/program-probes" / stamp
    folder.mkdir(parents=True, mode=0o700)
    original = original_png()
    (folder / "original.png").write_bytes(original)
    (folder / "original.png").chmod(0o600)
    metadata = {"upload_id": "reference", "mime_type": "image/png", "size_bytes": len(original),
                "sha256": hashlib.sha256(original).hexdigest()}
    database = folder / "store.sqlite"
    report = {"status": "failed", "device_installed": False, "physical_execution": False,
              "authoring_method": "managed_agent", "input_scope": "synthetic_image_and_diagnostic_text",
              "original_sha256": metadata["sha256"]}
    try:
        with ProgramStore(database) as store:
            store.bind_device("probe_session", "probe_device")
            intent = store.accept_intent("probe_session", "probe_device", "once",
                                        json.dumps({"prompt": PROMPT, "media": [metadata]}).encode())["intent_id"]
        broker = ProgramBroker(database, "probe_session", intent, folder / "tools",
                               {"reference": {"data": original, "mime_type": "image/png"}})
        input_blocks = [{"type": "text", "text": PROMPT},
                        {"type": "image", "mime_type": "image/png", "data": base64.b64encode(original).decode()}]
        selection = run_program_agent(input_blocks, job_dir=folder / "agent", tool_definitions=tool_definitions(),
                                      execute_tool=broker,
                                      progress=lambda stage, detail: print(json.dumps({"stage": stage}), flush=True))
        with ProgramStore(database) as store:
            body = store.candidate_bytes("probe_session", intent, selection["candidate_id"])
            if hashlib.sha256(body).hexdigest() != selection["sha256"]:
                raise ValueError("candidate_identity")
        result = execute_program(body, scenario(), deadline=time.monotonic() + 20)
        passed = verify_generated(body, result)
        asset_dependent = passed and check_asset_dependence(body)
        passed = passed and asset_dependent
        _write(folder / "independent-run.json", result.report)
        path = folder / "generated-app.json"
        path.write_bytes(body)
        path.chmod(0o600)
        for name, png in result.images:
            path = folder / ("observed-" + name + ".png")
            path.write_bytes(png)
            path.chmod(0o600)
        report.update(status="generated_and_independently_checked" if passed else "fidelity_failed",
                      independent_fidelity_passed=passed, package_sha256=selection["sha256"],
                      asset_dependence_passed=asset_dependent, source_authorship="managed_agent",
                      source_sha256=hashlib.sha256(json.loads(body)["source"].encode()).hexdigest(),
                      package_bytes=len(body), frame_count=len(result.images), runner_sha256=result.runner_sha256)
    except ProviderError as error:
        report["error_code"] = error.code
    except Exception:
        report["error_code"] = "probe_failed"
    report["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    report["observed_at_utc"] = datetime.now(timezone.utc).isoformat()
    evidence = ROOT / "artifacts/verification" / ("program-generation-" + stamp + ".json")
    evidence.parent.mkdir(parents=True, exist_ok=True)
    _write(evidence, report)
    print(json.dumps(report), flush=True)
    return 0 if report["status"] == "generated_and_independently_checked" else 1


if __name__ == "__main__":
    sys.exit(main())
