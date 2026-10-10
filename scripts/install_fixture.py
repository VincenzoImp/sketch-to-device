#!/usr/bin/env python3
"""Publish a labeled hardware-test fixture, or inspect its real device ACK.

This local bring-up tool does not call an AI provider or prove the phone flow.
Use while generation is idle. It replaces the device's desired package only
with --install; the default command makes no changes.
"""
import argparse
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).absolute().parent.parent
sys.path.insert(0, str(ROOT))
from backend.deployments import ConflictError, DeploymentStore
from backend.server import save_private
from runtime.validation import package_report

DIRECTORY = ROOT / "private/service"


def probe(directory, fixture=None):
    config = json.loads((directory / "demo-config.json").read_text())
    database = directory / "deployments.sqlite"
    record_path = directory / "fixture-last.json"
    if not database.is_file():
        raise ValueError("Service must already be configured")
    with DeploymentStore(database) as store:
        session, device = config["session_id"], config["device_id"]
        if fixture:
            raw = (ROOT / "contracts/fixtures" / (fixture + ".json")).read_bytes()
            report = package_report(raw)
            request = json.dumps({"kind": "hardware_fixture", "fixture": fixture,
                                  "source_sha256": report["sha256"]}).encode()
            try:
                intent = store.accept_intent(session, device, "fixture-" + uuid.uuid4().hex,
                                             request, require_idle=True)
            except ConflictError:
                return {"result": "generation_busy", "fixture_published": False}
            envelope = store.publish(session, intent["intent_id"], raw)
            save_private(record_path, {"fixture": fixture, "intent_id": intent["intent_id"],
                                       "deployment": envelope})
        record = json.loads(record_path.read_text())
        desired = store.desired_for_device(device)
        active = store.active_for_session(session, device)
        history = store.ack_history(session, record["intent_id"])
        exact = active == record["deployment"] and desired == record["deployment"]
        return {"kind": "hardware_fixture", "fixture": record["fixture"],
                "deployment": record["deployment"], "acknowledgments": history,
                "exact_device_ack_received": exact, "physical_touch_verified": False,
                "ai_generation_tested": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    options = parser.add_mutually_exclusive_group()
    options.add_argument("--install", choices=("tap-sprint", "focus-timer"))
    options.add_argument("--status", action="store_true")
    args = parser.parse_args()
    if not args.install and not args.status:
        print('{"result":"not_requested"}')
        return 0
    try:
        print(json.dumps(probe(DIRECTORY, args.install), indent=2))
        return 0
    except Exception:
        print('{"result":"fixture_probe_failed"}')
        return 1


if __name__ == "__main__":
    sys.exit(main())
