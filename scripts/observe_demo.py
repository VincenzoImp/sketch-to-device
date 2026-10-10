#!/usr/bin/env python3
"""Observe new local demo jobs without sending requests or modifying service data."""
import datetime
import json
import re
import sqlite3
import sys
import time
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).absolute().parent.parent
sys.path.insert(0, str(ROOT))
from backend.deployments import DeploymentStore
from backend.server import save_private
from scripts.probe_providers import SafeParser

STAGES = {"queued", "preparing", "understanding", "transcribing", "generating",
          "repairing", "validating", "simulating", "ready", "failed", "superseded"}
IDENTIFIER = re.compile(r"intent_[a-f0-9]{32}\Z")


class ReadOnlyStore(DeploymentStore):
    def __init__(self, path):
        self._db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True,
                                   timeout=0.1, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA query_only=ON")

    @contextmanager
    def _transaction(self):
        if self._db.in_transaction:
            yield
            return
        self._db.execute("BEGIN")
        try:
            yield
        finally:
            self._db.rollback()


def read_record(path):
    with path.open("rb") as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ValueError("Record too large")
    value = json.loads(raw)
    if type(value) is not dict:
        raise ValueError("Invalid record")
    return value


def job_snapshot(store, config, path):
    record = read_record(path)
    identifier = path.stem
    if not IDENTIFIER.fullmatch(identifier) or record.get("intent_id") != identifier:
        raise ValueError("Invalid job identity")
    stage = record.get("stage")
    if type(stage) is not str or stage not in STAGES:
        raise ValueError("Unknown stage")
    with store._transaction():
        intent = store.get_intent(config["session_id"], identifier)
        if intent["device_id"] != config["device_id"]:
            raise ValueError("Wrong device")
        desired = store.desired_for_device(config["device_id"])
        active = store.active_for_session(config["session_id"], config["device_id"])
        exact = bool(desired and desired == active and desired["sequence"] == intent["sequence"]
                     and intent["status"] == "published"
                     and any(ack["status"] == "active" for ack in store.ack_history(config["session_id"], identifier)))
        if intent["status"] in {"failed", "superseded"}:
            stage = intent["status"]
        return {"stage": "active" if exact else stage, "intent_id": identifier,
                "desired": desired, "active": active, "exact_active_ack_observed": exact}


def observe(directory, output, seconds, emit=print, clock=time.monotonic, sleep=time.sleep):
    config = read_record(directory / "demo-config.json")
    baseline = {path.name for path in (directory / "jobs").glob("*.json")}
    started = clock()
    seen, last = {}, {}
    report = {"result": "watching", "timing_basis": "observer_first_saw_job_not_phone_submission",
              "baseline_jobs_excluded": len(baseline), "events": []}
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    save_private(output, report)
    with ReadOnlyStore(directory / "deployments.sqlite") as store:
        while clock() - started < seconds:
            for path in (directory / "jobs").glob("*.json"):
                if clock() - started >= seconds:
                    break
                if path.name in baseline:
                    continue
                try:
                    state = job_snapshot(store, config, path)
                except (OSError, ValueError, sqlite3.Error):
                    continue  # Private malformed content and exception text never leave this process.
                now = clock()
                if path.name not in seen:
                    seen[path.name] = (len(seen) + 1, now)
                if last.get(path.name) == state:
                    continue
                last[path.name] = state
                event = dict(state, job=seen[path.name][0], elapsed_ms=round((now - seen[path.name][1]) * 1000),
                             observed_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
                report["events"].append(event)
                if state["exact_active_ack_observed"]:
                    report["result"] = "exact_active_ack_observed"
                save_private(output, report)
                emit(json.dumps(event))
                if state["exact_active_ack_observed"]:
                    return report
            sleep(min(0.25, max(0, seconds - (clock() - started))))
    report["result"] = "observation_window_ended"
    save_private(output, report)
    return report


def main(argv=None):
    parser = SafeParser(description=__doc__)
    parser.add_argument("--seconds", type=int, help="explicitly watch new jobs for 1–600 seconds")
    args = parser.parse_args(argv)
    if args.seconds is None:
        print('{"result":"not_requested"}')
        return 0
    if not 1 <= args.seconds <= 600:
        parser.error("Observation duration must be between 1 and 600 seconds")
    try:
        report = observe(ROOT / "private/service", ROOT / "artifacts/verification/demo-observation.json", args.seconds)
        print(json.dumps({"result": report["result"], "observed_events": len(report["events"])}))
        return 0
    except Exception:
        print('{"result":"observer_failed"}')
        return 1


if __name__ == "__main__":
    sys.exit(main())
