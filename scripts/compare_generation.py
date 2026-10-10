#!/usr/bin/env python3
"""Compare two live managed models on one public request; never install an app."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import time

ROOT = Path(__file__).absolute().parent.parent
MODELS = ("gemini-3.5-flash-lite", "gemini-3.8-flash")
COLORS = ("#FF69B4", "#164EAD", "#80FF80", "#FF69B4", "#164EAD", "#80FF80", "#FF69B4")
PROMPT = ('Create an app called "Hello Colors" with exactly one visible clickable button labeled '
          '"Hello World". Its initial background must be pink (#FF69B4). Each press changes the '
          'button background in this repeating order: blue (#164EAD), green (#80FF80), then pink '
          '(#FF69B4). Preserve the exact Hello World label in every state. Optional static labels '
          'are allowed; no timer or other controls. Use the current documented device runtime. '
          'Use targeted documentation lookup as needed; no web research is required for this request.')
PHASES = ("input_preparation", "managed_generation", "artifact_download", "host_checks", "cleanup")


def save(path, raw):
    with os.fdopen(os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def save_json(path, value):
    save(path, json.dumps(value, sort_keys=True, indent=2).encode())


def context_hash():
    from backend.generator import PUBLIC_FILES, SDK_FILES, MANAGED_TOOLS
    digest = hashlib.sha256(json.dumps(list(MANAGED_TOOLS)).encode())
    for name in ("backend/generator.py", "backend/providers.py") + PUBLIC_FILES + SDK_FILES:
        digest.update(name.encode() + b"\0" + (ROOT / name).read_bytes() + b"\0")
    return digest.hexdigest()


def fidelity(raw):
    """Execute the actual reference runtime; schema validity alone cannot pass."""
    from runtime.reference import ReferenceRuntime
    from runtime.validation import CAPABILITIES
    runtime = ReferenceRuntime(raw)
    if runtime.app["name"] != "Hello Colors" or runtime.app["version"] != 1 or runtime.timers:
        return False
    accent = CAPABILITIES["palettes"][runtime.app["theme"]["palette"]]["accent"]
    for index, expected in enumerate(COLORS):
        visible = [runtime.widgets[key] for key in runtime.visible[runtime.screen]]
        buttons = [item for item in visible if item["type"] == "button"]
        if (len(buttons) != 1 or any(item["type"] not in {"button", "label"} for item in visible)
                or buttons[0]["text"] != "Hello World"
                or buttons[0].get("background_color", accent).upper() != expected):
            return False
        if index < len(COLORS) - 1 and runtime.press(buttons[0]["id"], index + 1, runtime.event_token()) != "applied":
            return False
    return not runtime.errors


def archive(provider, case, report):
    """Copy only files carrying this call's exact run ID, never a stale last result."""
    run_id = report.get("timing", {}).get("run_id") if type(report.get("timing")) is dict else None
    result = {"trace_archived": False, "timing_archived": False}
    if type(run_id) is not str or not re.fullmatch(r"[a-f0-9]{32}", run_id):
        return result
    for kind, name in (("trace", "managed-last-execution.json"), ("timing", "managed-last-timing.json")):
        try:
            descriptor = os.open(str(provider / name), os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(descriptor, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    continue
                raw = stream.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                continue
            value = json.loads(raw)
            if type(value) is not dict or value.get("run_id") != run_id:
                continue
            save(case / name, raw)
            result[kind + "_archived"] = True
        except (OSError, ValueError):
            continue
    return result


def compare(private, generator, job_seconds=600, emit=print):
    from backend.generator import PROGRESS
    from backend.providers import ERROR_MESSAGES
    if type(job_seconds) is not int or job_seconds not in (180, 600):
        raise ValueError("invalid comparison duration")
    directory = private / "comparisons"
    if private.is_symlink() or directory.is_symlink():
        raise ValueError("invalid private directory")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    run = Path(tempfile.mkdtemp(prefix="hello-colors-", dir=str(directory)))
    frozen_context = context_hash()
    save(run / "prompt.txt", PROMPT.encode())
    result = {"result": "comparison_finished", "device_installed": False, "cases": [],
              "fidelity_scope": "host initial state and six presses; no physical execution",
              "comparison_scope": "single sequential diagnostic; no statistical model ranking",
              "elapsed_basis": "local generator call and independent fidelity checks",
              "context_sha256": frozen_context, "prompt_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(),
              "observed_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    for index, model in enumerate(MODELS, 1):
        case = run / str(index)
        case.mkdir(mode=0o700)
        report = {}
        item = {"model": model, "token_budget": 200000, "job_seconds": job_seconds,
                "result": "generation_failed", "fidelity_passed": False, "phase_ms": {}}
        def progress(stage, _detail):
            if type(stage) is str and stage in PROGRESS:
                emit(json.dumps({"case": index, "model": model, "stage": stage}))
        started = time.monotonic()
        if context_hash() != frozen_context:
            item.update(result="context_changed", code="context_changed")
        else:
            try:
                raw = generator(PROMPT, [], progress, model=model, token_budget=200000,
                                job_seconds=job_seconds, report=report)
                if type(raw) is not bytes or not 1 <= len(raw) <= 65536:
                    raise ValueError("invalid generated artifact")
                save(case / "app.json", raw)
                item.update(sha256=hashlib.sha256(raw).hexdigest(), size_bytes=len(raw))
                try:
                    passed = fidelity(raw)
                except ValueError:
                    passed = False
                item.update(result="fidelity_passed" if passed else "fidelity_failed", fidelity_passed=passed)
            except Exception as exc:
                code = getattr(exc, "code", None)
                item["code"] = code if type(code) is str and code in ERROR_MESSAGES else "generation"
        item["elapsed_ms"] = round((time.monotonic() - started) * 1000)
        if context_hash() != frozen_context:
            item.update(result="context_changed", fidelity_passed=False)
        timing = report.get("timing", {})
        phases = timing.get("phase_ms", {}) if type(timing) is dict else {}
        if type(phases) is dict:
            item["phase_ms"] = {key: phases[key] for key in PHASES
                                if type(phases.get(key)) is int and 0 <= phases[key] <= 10**12}
        save_json(case / "report.json", report)
        item.update(archive(private / "provider", case, report))
        save_json(case / "summary.json", item)
        result["cases"].append(item)
        emit(json.dumps(item))
        if item["result"] == "context_changed":
            break
    save_json(run / "summary.json", result)
    emit(json.dumps(result))
    return result, run


class Parser(argparse.ArgumentParser):
    def error(self, _message):
        self.exit(2, '{"result":"invalid_arguments"}\n')


def main(argv=None):
    parser = Parser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="run two sequential paid provider generations")
    parser.add_argument("--job-seconds", type=int, choices=(180, 600), default=600)
    args = parser.parse_args(argv)
    if not args.live:
        print('{"result":"live_not_requested"}')
        return 0
    sys.path.insert(0, str(ROOT))
    try:
        from backend.generator import generate_app
        result, _ = compare(ROOT / "private", generate_app, args.job_seconds)
        return 0 if len(result["cases"]) == 2 and all(item["fidelity_passed"] for item in result["cases"]) else 1
    except Exception:
        print('{"result":"comparison_record_failed"}')
        return 1


if __name__ == "__main__":
    sys.exit(main())
