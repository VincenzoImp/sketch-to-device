"""Real HTTP dispatch, native JS execution and SQLite; agent behavior is fake."""

import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from backend.program_generation import generate_program
from backend.server import Application
from tests.test_device_runtime import report
from tests.test_service import http


def identity(envelope):
    return {"deployment_id": envelope["deployment_id"], "sequence": envelope["sequence"],
            **{key: envelope["manifest"][key] for key in ("app_id", "version", "sha256")}}


class ProgramServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.folder = Path(self.temporary.name)
        self.calls = 0
        self.after_selection = lambda: None
        self.clock = [100.0]
        self.patched = patch("backend.device_runtime.time.time", side_effect=lambda: self.clock[0])
        self.patched.start()
        self.app = Application(self.folder, program_generator=self.generate)

    def tearDown(self):
        self.idle()
        self.patched.stop()
        self.temporary.cleanup()

    def idle(self):
        deadline = time.monotonic() + 5
        while self.app.busy and time.monotonic() < deadline:
            time.sleep(.005)
        self.assertFalse(self.app.busy)

    def generate(self, *args):
        self.calls += 1
        # This fixed diagnostic belongs only to the test, never product authoring.
        def fake_agent(blocks, **kwargs):
            broker = kwargs["execute_tool"]
            value = {"app_id": "service_probe", "name": "Service Probe",
                     "source": "gfx.begin('#FF0000');gfx.end();", "requires": ["canvas"],
                     "asset_refs": [], "scenario": {"version": 1, "seed": 1,
                     "initial_time_ms": 0, "wall_time": None,
                     "events": [{"type": "frame", "name": "initial"}]}}
            result = broker("run_app", value, "run", time.monotonic() + 10)
            if result.is_error:
                raise AssertionError(result.content)
            receipt = json.loads(result.content[0]["text"])["receipt_id"]
            return broker("submit_app", {"receipt_id": receipt}, "submit", time.monotonic() + 10).submission
        selected = generate_program(*args, client=type("UnusedProvider", (), {})(), agent=fake_agent)
        self.after_selection()
        return selected

    def runtime(self, role="device", **changes):
        body = report(device_id=self.app.config["device_id"], **changes)
        return http(self.app, "POST", "/api/device/runtime", role, json.dumps(body).encode())

    def start(self, key="a" * 32):
        return http(self.app, "POST", "/api/generate", body=json.dumps(
            {"request_id": key, "prompt": "A diagnostic app", "uploads": []}).encode())

    def job(self, key="a" * 32):
        code, _, payload = self.start(key)
        self.assertEqual(code, 202, payload)
        identifier = json.loads(payload)["job_id"]
        self.idle()
        return identifier

    def desired(self):
        return json.loads(http(self.app, "GET", "/api/device/desired", "device")[2])["desired"]

    def ack(self, envelope):
        return http(self.app, "POST", "/api/device/ack", "device", json.dumps({
            **identity(envelope), "device_id": self.app.config["device_id"], "status": "active"}).encode())

    def test_fresh_compatible_authenticated_target_required_before_generation(self):
        for role in ("session", "invalid"):
            self.assertEqual(self.runtime(role)[0], 401)
        code, _, payload = self.start()
        self.assertEqual((code, json.loads(payload)["error"]), (409, "capabilities_missing"))
        self.assertEqual(self.calls, 0)
        self.assertEqual(self.runtime(runtime_version="0.2.0", schema_versions=[1])[0], 200)
        code, _, payload = self.start()
        self.assertEqual((code, json.loads(payload)["error"]), (409, "capabilities_incompatible"))
        self.clock[0] += 1
        self.assertEqual(self.runtime()[0], 200)
        self.clock[0] += 31
        code, _, payload = self.start()
        self.assertEqual((code, json.loads(payload)["error"]), (409, "capabilities_stale"))
        self.assertEqual(self.calls, 0)
        with self.app.store() as store:
            self.assertEqual(store._db.execute("SELECT COUNT(*) FROM intents").fetchone()[0], 0)

    def test_tested_exact_package_download_and_ack_then_stale_download_gate(self):
        self.runtime()
        identifier = self.job()
        envelope = self.desired()
        self.assertEqual(envelope["manifest"]["schema_version"], 2)
        code, _, raw = http(self.app, "GET", envelope["manifest"]["download_path"], "device")
        self.assertEqual(code, 200)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), envelope["manifest"]["sha256"])
        with self.app.store() as store:
            candidate = store._db.execute("SELECT body FROM program_candidates").fetchone()[0]
            self.assertEqual(raw, candidate)
        self.assertEqual(self.app.status(identifier)["stage"], "ready")
        self.assertEqual(self.ack(envelope)[0], 200)
        self.assertEqual(self.app.status(identifier)["stage"], "active")
        self.clock[0] += 31
        code, _, payload = http(self.app, "GET", envelope["manifest"]["download_path"], "device")
        self.assertEqual((code, json.loads(payload)["error"]), (409, "capabilities_stale"))
        self.assertEqual(self.calls, 1)
        self.assertEqual(json.loads(self.start()[2])["job_id"], identifier)

    def test_expired_target_keeps_selection_across_restart_then_publishes_without_regeneration(self):
        self.runtime()
        self.after_selection = lambda: self.clock.__setitem__(0, 131)
        identifier = self.job()
        self.assertEqual(self.app.status(identifier)["stage"], "waiting_device")
        self.assertIsNone(self.desired())
        selected = self.app.selection_path(identifier).read_bytes()
        self.app = Application(self.folder, program_generator=self.generate)
        self.assertEqual(self.app.status(identifier)["stage"], "waiting_device")
        self.assertEqual(self.calls, 1)
        self.assertEqual(self.runtime()[0], 200)
        self.assertEqual(self.app.status(identifier)["stage"], "ready")
        self.assertEqual(self.calls, 1)
        self.assertEqual(self.app.selection_path(identifier).read_bytes(), selected)
        self.assertEqual(self.desired()["manifest"]["sha256"], json.loads(selected)["sha256"])

    def test_fault_recovery_status_wins_historical_and_late_active_ack(self):
        self.runtime()
        first_id = self.job(); first = self.desired()
        self.ack(first)
        second_id = self.job("b" * 32); second = self.desired()
        self.ack(second)
        self.assertEqual(self.app.status(second_id)["stage"], "active")
        report_body = {"protocol_version": 1, "report_id": "recovery-one", "recovery_seq": 1,
                       "failed": identity(second), "recovered": identity(first), "error_code": "runtime_error"}
        body = json.dumps(report_body).encode()
        self.assertEqual(http(self.app, "POST", "/api/device/recovery", "session", body)[0], 401)
        code, _, payload = http(self.app, "POST", "/api/device/recovery", "device", body)
        self.assertEqual(code, 200)
        self.assertTrue(json.loads(payload)["recorded"])
        state = self.app.status(second_id)
        self.assertEqual(state["stage"], "recovered")
        self.assertIn("previous app", state["detail"])
        code, _, payload = self.ack(second)
        self.assertEqual(code, 200)
        self.assertFalse(json.loads(payload)["current_success"])
        self.assertEqual(self.app.status(second_id)["stage"], "recovered")
        self.assertFalse(json.loads(http(self.app, "POST", "/api/device/recovery", "device", body)[2])["recorded"])
        with self.app.store() as store:
            self.assertEqual(store.active_for_session(self.app.config["session_id"], self.app.config["device_id"])["deployment_id"], first["deployment_id"])
            self.assertIsNone(store.recovery_for_intent(self.app.config["session_id"], first_id))


if __name__ == "__main__":
    unittest.main()
