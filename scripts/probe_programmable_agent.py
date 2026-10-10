#!/usr/bin/env python3
"""G0: a real managed custom-tool round trip to a fixed trusted host UI proof.

Default is inert. --live uses Google quota but never installs an app. The tool
runs the existing accepted native proof, not arbitrary agent-authored code.
Official protocol: https://ai.google.dev/gemini-api/docs/antigravity-agent#function-calling
"""

import argparse
import base64
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import secrets
import struct
import subprocess
import sys
import tempfile
import time
import uuid
import zlib

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
from backend.providers import ProviderClient, ProviderError, safe_diagnostics
from scripts import probe_programmable_ui as ui

AGENT = "antigravity-preview-09-2026"
MODEL = "gemini-3.5-flash-lite"
TOOL_NAME = "run_trusted_ui_proof"
ARGUMENTS = {"proof": "builtin_ui_baseline"}
TERMINAL = {"completed", "failed", "cancelled", "incomplete"}
STATES = TERMINAL | {"queued", "in_progress", "requires_action"}
TOOL = {"type": "function", "name": TOOL_NAME,
        "description": "Run a fixed, trusted QuickJS/LVGL native host proof. This does not validate generated code.",
        "parameters": {"type": "object", "properties": {
            "proof": {"type": "string", "enum": ["builtin_ui_baseline"]}},
            "required": ["proof"], "additionalProperties": False}}
PUBLIC_INPUT = ("Call run_trusted_ui_proof exactly once with proof builtin_ui_baseline. "
                "This is a protocol test, not app generation. The result contains an actual "
                "rendered screenshot. Inspect that image and finish with ONLY a JSON object "
                "with visible_title, button_text and button_color string fields. Copy the "
                "visible title and button text, and use the common English name of the "
                "button's background color. Do not inspect files, execute code, research, "
                "or request any other tool. Do not infer image contents from the receipt.")
FAILURES = {"invalid_identity", "invalid_state", "identity_changed", "wrong_agent",
            "invalid_steps", "unexpected_tool", "invalid_tool_arguments", "missing_tool_call",
            "tool_already_executed", "not_completed", "host_proof_unavailable", "host_proof_failed",
            "host_proof_timeout", "unsafe_output_path", "evidence_too_large", "internal_probe_error",
            "evidence_write_failed", "image_invalid", "image_observation_failed", "interrupted"}


def ppm_png(raw):
    """Losslessly encode the fixed trusted renderer's P6 RGB pixels as PNG."""
    header = b"P6\n320 480\n255\n"
    if not raw.startswith(header) or len(raw) != len(header) + 320 * 480 * 3:
        raise Failure("image_invalid")
    pixels = raw[len(header):]
    rows = b"".join(b"\x00" + pixels[y * 960:(y + 1) * 960] for y in range(480))
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 320, 480, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def image_observation(value, expected):
    parts = []
    steps = value.get("steps", [])
    if type(steps) is not list:
        return False
    for step in steps:
        if type(step) is dict and step.get("type") == "model_output":
            contents = step.get("content", [])
            if type(contents) is not list:
                return False
            for content in contents:
                if type(content) is dict and content.get("type") == "text" and type(content.get("text")) is str:
                    parts.append(content["text"])
    raw = "".join(parts).strip()
    if raw.startswith("```json\n") and raw.endswith("\n```"):
        raw = raw[8:-4]
    try:
        observed = json.loads(raw) if len(raw) <= 2048 else None
    except (ValueError, TypeError):
        observed = None
    if type(observed) is not dict or set(observed) != {"visible_title", "button_text", "button_color"}:
        return False
    normalized = {key: " ".join(item.casefold().split()) for key, item in observed.items()
                  if type(item) is str and len(item) <= 128}
    return (normalized.get("visible_title") == "hello world"
            and normalized.get("button_text") == "change color"
            and normalized.get("button_color") in {
                "pink": {"pink", "hot pink"}, "blue": {"blue", "light blue"},
                "green": {"green", "light green"}}[expected])


class Failure(Exception):
    def __init__(self, code):
        self.code = code if code in FAILURES else "internal_probe_error"
        super().__init__(self.code)


def identifier(value):
    if type(value) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{1,4096}", value):
        raise Failure("invalid_identity")
    return value


def atomic_json(path, value):
    raw = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    if len(raw) > 2 * 1024 * 1024:
        raise Failure("evidence_too_large")
    if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != ROOT.parent):
        raise Failure("unsafe_output_path")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".g0-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as target:
            os.fchmod(target.fileno(), 0o600)
            target.write(raw)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def pending_call(response):
    steps = response.get("steps", [])
    if type(steps) is not list or len(steps) > 512 or any(type(s) is not dict for s in steps):
        raise Failure("invalid_steps")
    executed = {identifier(s.get("call_id")) for s in steps if s.get("type") == "function_result"}
    calls = [s for s in steps if s.get("type") == "function_call" and identifier(s.get("id")) not in executed]
    if not calls:
        raise Failure("missing_tool_call")
    if len(calls) != 1 or calls[0].get("name") != TOOL_NAME:
        raise Failure("unexpected_tool")
    call = calls[0]
    identifier(call.get("id"))
    if type(call.get("arguments")) is not dict or call["arguments"] != ARGUMENTS:
        raise Failure("invalid_tool_arguments")
    return call


def host_proof(deadline):
    """Run the fixed executable after main's dependency preflight, within the job."""
    binary = ui.BASE / "build/ui_probe"
    source = ui.PROJECT / "ui_probe.c"
    try:
        if time.monotonic() >= deadline:
            raise ProviderError("deadline")
        if binary.is_symlink() or not binary.is_file() or not os.access(binary, os.X_OK):
            raise Failure("host_proof_unavailable")
        binary_bytes, source_bytes = binary.read_bytes(), source.read_bytes()
        if len(binary_bytes) > 16 * 1024 * 1024 or len(source_bytes) > 65536:
            raise Failure("host_proof_unavailable")
        with tempfile.TemporaryDirectory(prefix="g0-trusted-ui-") as temporary:
            work = Path(temporary)
            executable, result_path = work / "ui_probe", work / "result.json"
            executable.write_bytes(binary_bytes)
            executable.chmod(0o700)
            with result_path.open("wb") as output:
                os.fchmod(output.fileno(), 0o600)
                process = subprocess.Popen([str(executable)], cwd=work, stdout=output,
                                           stderr=subprocess.DEVNULL, start_new_session=True,
                                           env={"PATH": "/usr/bin:/bin", "TMPDIR": temporary}, umask=0o077)
                try:
                    process.wait(timeout=max(0.01, min(20, deadline - time.monotonic())))
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
                    raise Failure("host_proof_timeout") from None
            if process.returncode:
                raise Failure("host_proof_failed")
            checked = ui.checked_result(result_path)
            frames = {}
            for name in ("color-0.ppm", "color-1.ppm", "color-2.ppm", "color-3.ppm", "calculation.ppm"):
                raw = (work / name).read_bytes()
                if len(raw) != 460815:
                    raise Failure("host_proof_failed")
                frames[name] = hashlib.sha256(raw).hexdigest()
            selected = secrets.randbelow(3)
            frame = (work / ("color-" + str(selected) + ".ppm")).read_bytes()
            image = ppm_png(frame)
            receipt = {"scope": "fixed_builtin_host_ui_proof_only", "generated_code_validated": False,
                    "physical_execution": False, "binary_sha256": hashlib.sha256(binary_bytes).hexdigest(),
                    "observed_source_sha256": hashlib.sha256(source_bytes).hexdigest(),
                    "checks": checked, "framebuffer_sha256": frames,
                    "image_sha256": hashlib.sha256(image).hexdigest(), "image_bytes": len(image)}
            return receipt, image, ("pink", "blue", "green")[selected]
    except ui.ProbeError:
        raise Failure("host_proof_failed") from None
    except OSError:
        raise Failure("host_proof_unavailable") from None


def probe(client, checker, deadline, *, sleep=time.sleep, clock=time.monotonic, journal=None):
    """One custom call and one continuation; no retry or automatic fallback."""
    started = clock()
    report = {"result": "failed", "model": MODEL, "token_budget": 200000, "job_seconds": 600,
              "requires_action_observed": False, "local_tool_executions": 0,
              "matching_call_id_submitted": False, "same_environment_submitted": False,
              "continuation_completed": False, "generated_code_validated": False,
              "image_result_submitted": False, "image_observation_matched": False,
              "device_installation": False, "cancellation": "not_needed"}
    trace = {"scope": "fixed_builtin_host_ui_proof_only", "responses": {}}
    current_id, state, environment = None, None, None
    submission_unresolved = False

    def persist():
        trace["resume_state"] = {"last_known_interaction_id": current_id, "status": state,
                                 "environment_id": environment, "submission_unresolved": submission_unresolved}
        if journal:
            try:
                journal(trace)
            except (OSError, Failure):
                raise Failure("evidence_write_failed") from None

    def record(value, phase, expected=None):
        nonlocal current_id, state, environment, submission_unresolved
        candidate_id = identifier(value.get("id"))
        if expected is not None and candidate_id != expected:
            raise Failure("identity_changed")
        current_id = candidate_id
        submission_unresolved = False
        state = value.get("status")
        if type(state) is not str or state not in STATES:
            state = None
            raise Failure("invalid_state")
        if value.get("agent") is not None and value.get("agent") != AGENT:
            raise Failure("wrong_agent")
        if value.get("environment_id") is not None:
            env = identifier(value["environment_id"])
            if environment is not None and env != environment:
                raise Failure("identity_changed")
            environment = env
        trace["responses"][phase] = value
        report[phase + "_status"] = state
        persist()
        return value

    def settle(value, phase):
        value = record(value, phase)
        while state in {"queued", "in_progress"}:
            if clock() >= deadline:
                raise ProviderError("deadline")
            sleep(min(1, max(0, deadline - clock())))
            if clock() >= deadline:
                raise ProviderError("deadline")
            expected = current_id
            value = record(client.google("GET", "/v1beta/interactions/" + expected), phase, expected)
        return value

    try:
        profile = {"type": "antigravity", "model": MODEL, "max_total_tokens": 200000}
        if clock() >= deadline:
            raise ProviderError("deadline")
        submission_unresolved = True
        persist()
        first = settle(client.interaction({"agent": AGENT, "input": PUBLIC_INPUT,
                      "environment": {"type": "remote", "network": "disabled"},
                      "tools": [TOOL], "agent_config": profile, "background": True, "store": True}), "initial")
        if state != "requires_action":
            raise Failure("missing_tool_call")
        identifier(environment)
        report["requires_action_observed"] = True
        call = pending_call(first)
        if clock() >= deadline:
            raise ProviderError("deadline")
        receipt, rendered, expected_color = checker(deadline)
        report["local_tool_executions"] = 1
        report["receipt"] = receipt
        previous, previous_environment = current_id, environment
        continuation = {"agent": AGENT, "previous_interaction_id": previous,
                        "environment": previous_environment, "agent_config": profile,
                        "background": True, "store": True,
                        "input": [{"type": "function_result", "name": TOOL_NAME,
                                   "call_id": call["id"], "result": [
                                       {"type": "text", "text": json.dumps(receipt, sort_keys=True)},
                                       {"type": "image", "mime_type": "image/png",
                                        "data": base64.b64encode(rendered).decode("ascii")}]}]}
        trace["continuation"] = continuation
        trace["expected_image_color"] = expected_color
        if clock() >= deadline:
            raise ProviderError("deadline")
        # Retain the known previous ID if the create response is lost. Its cancel
        # does not establish cancellation of an unknown accepted continuation.
        submission_unresolved = True
        persist()
        final = settle(client.interaction(continuation), "continuation")
        report["matching_call_id_submitted"] = True
        report["same_environment_submitted"] = True
        report["image_result_submitted"] = True
        if state != "completed":
            raise Failure("not_completed")
        report["continuation_completed"] = True
        report["image_observation_matched"] = image_observation(final, expected_color)
        if not report["image_observation_matched"]:
            raise Failure("image_observation_failed")
        report["usage"] = safe_diagnostics({"usage": final.get("usage")}).get("usage", {})
        report["result"] = "managed_custom_tool_roundtrip_passed"
    except (Failure, ProviderError) as error:
        report["error_code"] = error.code
        if isinstance(error, ProviderError):
            report["diagnostics"] = safe_diagnostics(error.diagnostics)
    except KeyboardInterrupt:
        report["error_code"] = "interrupted"
    finally:
        if state not in TERMINAL or submission_unresolved:
            report["cancellation"] = "unconfirmed"
            if current_id is not None:
                try:
                    client.deadline = clock() + 9
                    cancelled = client.google("POST", "/v1beta/interactions/" + current_id + "/cancel", {})
                    if (not submission_unresolved and cancelled.get("id") == current_id
                            and cancelled.get("status") == "cancelled"):
                        report["cancellation"] = "confirmed"
                except (ProviderError, Failure):
                    pass
        report["elapsed_ms"] = max(0, int((clock() - started) * 1000))
        report["remote_job_may_continue"] = report["cancellation"] == "unconfirmed"
        trace["report"] = report
        try:
            persist()
        except Failure:
            report.update(result="failed", error_code="evidence_write_failed")
    return report, trace


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="use Google and run the fixed local host proof once")
    args = parser.parse_args(argv)
    if not args.live:
        print(json.dumps({"result": "not_run", "live_required": True,
                          "generated_code_validated": False, "device_installation": False}))
        return 0
    started = datetime.datetime.now(datetime.timezone.utc)
    run_id = uuid.uuid4().hex
    name = started.strftime("%Y%m%dT%H%M%S") + "-" + run_id[:8]
    trace_path = ROOT / "private/provider" / ("programmable-g0-" + name + ".json")
    def journal(value):
        atomic_json(trace_path, dict(value, run_id=run_id, started_at=started.isoformat()))
    try:
        # Verify fixed proof dependencies before spending provider quota.
        ui.status()
        deadline = time.monotonic() + 590
        client = ProviderClient(deadline)
        report, trace = probe(client, host_proof, deadline, journal=journal)
    except (Failure, ProviderError, ui.ProbeError, OSError):
        report, trace = {"result": "failed", "error_code": "local_preflight_failed"}, {}
    report.update({"run_id": run_id, "started_at": started.isoformat(),
                   "finished_at": datetime.datetime.now(datetime.timezone.utc).isoformat()})
    trace.update({"run_id": run_id, "started_at": report["started_at"], "finished_at": report["finished_at"]})
    try:
        atomic_json(trace_path, trace)
        atomic_json(ROOT / "artifacts/verification" / ("programmable-agent-g0-" + name + ".json"), report)
    except (Failure, OSError):
        print(json.dumps({"result": "failed", "error_code": "evidence_write_failed"}))
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0 if report["result"] == "managed_custom_tool_roundtrip_passed" else 1



if __name__ == "__main__":
    raise SystemExit(main())
