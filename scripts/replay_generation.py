#!/usr/bin/env python3
"""Replay the latest failed frozen request for diagnostics; never publish an app."""
import datetime
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).absolute().parent.parent
sys.path.insert(0, str(ROOT))
from backend.generator import PROGRESS, generate_app
from backend.providers import ERROR_MESSAGES, safe_diagnostics
from backend.server import MAX_TOTAL_MEDIA, MAX_UPLOAD, MEDIA_TYPES, save_private
from runtime.validation import package_report
from scripts.observe_demo import ReadOnlyStore, read_record
from scripts.probe_providers import SafeParser


class ReplayError(ValueError):
    def __init__(self, code):
        self.code = code


def frozen_input(directory):
    config = read_record(directory / "demo-config.json")
    with ReadOnlyStore(directory / "deployments.sqlite") as store:
        with store._transaction():
            device = store._device(config["device_id"], config["session_id"])
            if device["current_intent_id"]:
                current = store.get_intent(config["session_id"], device["current_intent_id"])
                if current["status"] == "accepted":
                    raise ReplayError("generation_busy")
            request = None
            rows = store._db.execute(
                "SELECT request FROM intents WHERE session_id=? AND device_id=? AND status='failed' ORDER BY sequence DESC LIMIT 100",
                (config["session_id"], config["device_id"]))
            for row in rows:
                raw = row["request"]
                if type(raw) is not bytes or not 1 <= len(raw) <= 65536:
                    continue
                try:
                    candidate = json.loads(raw)
                except ValueError:
                    continue
                if type(candidate) is dict and set(candidate) == {"prompt", "media"}:
                    request = candidate
                    break
    if request is None:
        raise ReplayError("replay_no_failed_job")
    if (type(request) is not dict or set(request) != {"prompt", "media"}
            or type(request["prompt"]) is not str or len(request["prompt"]) > 6000
            or type(request["media"]) is not list or len(request["media"]) > 3):
        raise ReplayError("replay_input_invalid")
    snapshots, total = [], 0
    for item in request["media"]:
        if (type(item) is not dict or set(item) != {"upload_id", "mime_type", "size_bytes", "sha256"}
                or type(item["upload_id"]) is not str or not re.fullmatch(r"[a-f0-9]{32}", item["upload_id"])
                or type(item["mime_type"]) is not str or item["mime_type"] not in MEDIA_TYPES
                or type(item["size_bytes"]) is not int or not 1 <= item["size_bytes"] <= MAX_UPLOAD
                or type(item["sha256"]) is not str or not re.fullmatch(r"[a-f0-9]{64}", item["sha256"])):
            raise ReplayError("replay_input_invalid")
        path = directory / "uploads" / item["upload_id"]
        if path.is_symlink():
            raise ReplayError("replay_input_invalid")
        with path.open("rb") as stream:
            data = stream.read(MAX_UPLOAD + 1)
        total += len(data)
        if (total > MAX_TOTAL_MEDIA or len(data) != item["size_bytes"]
                or hashlib.sha256(data).hexdigest() != item["sha256"]):
            raise ReplayError("replay_input_invalid")
        snapshots.append((item["mime_type"], data))
    if not request["prompt"].strip() and not snapshots:
        raise ReplayError("replay_input_invalid")
    return request["prompt"], snapshots


def save_bytes(path, raw):
    descriptor, temporary = tempfile.mkstemp(prefix="replay-", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, str(path))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def replay(directory, output, generator=generate_app, emit=print):
    report = {"result": "failed", "code": "replay_input_invalid", "diagnostics": {}, "device_installed": False}
    try:
        prompt, snapshots = frozen_input(directory)
        def progress(stage, _detail):
            if type(stage) is str and stage in PROGRESS:
                emit(json.dumps({"stage": stage}))
        with tempfile.TemporaryDirectory(prefix="sketch-replay-") as temporary:
            media = []
            for index, (mime, raw) in enumerate(snapshots):
                path = Path(temporary) / str(index)
                save_bytes(path, raw)
                media.append({"path": path, "mime_type": mime})
            try:
                artifact = generator(prompt, media, progress)
                checked = package_report(artifact)
            except Exception as exc:
                code = getattr(exc, "code", "generation")
                report.update(code=code if type(code) is str and code in ERROR_MESSAGES else "generation",
                              diagnostics=safe_diagnostics(getattr(exc, "diagnostics", None)))
            else:
                output.mkdir(parents=True, exist_ok=True, mode=0o700)
                save_bytes(output / "replayed-app.json", artifact)
                report = {"result": "replayed_and_host_validated", "sha256": checked["sha256"],
                          "size_bytes": checked["size_bytes"], "artifact": "artifacts/replayed-app.json",
                          "device_installed": False}
    except ReplayError as exc:
        report["code"] = exc.code
    except Exception:
        pass  # Private input, file paths and raw exception messages are never printed.
    report["observed_at_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    save_private(output / "replay-last-result.json", report)
    emit(json.dumps(report))
    return report


def main(argv=None):
    parser = SafeParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="authorize one real provider diagnostic replay")
    parser.add_argument("--last-failed", action="store_true", help="select the latest failed frozen service request")
    args = parser.parse_args(argv)
    if not args.live:
        print('{"result":"live_not_requested"}')
        return 0
    if not args.last_failed:
        parser.error("Live replay requires --last-failed")
    try:
        report = replay(ROOT / "private/service", ROOT / "artifacts")
        return 0 if report["result"] == "replayed_and_host_validated" else 1
    except Exception:
        print('{"result":"replay_record_failed"}')
        return 1


if __name__ == "__main__":
    sys.exit(main())
