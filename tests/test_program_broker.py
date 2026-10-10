"""Real broker/native/SQLite boundaries; authored snippets are platform tests."""

import base64
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from backend.deployments import ConflictError, StoreError
from backend.program_broker import ProgramBroker, tool_definitions
from backend.program_runner import execute_program, png_from_rgb
from backend.program_store import ProgramStore


class BrokerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.folder = Path(self.temporary.name)
        self.database = self.folder / "database.sqlite"
        # A real decodable original, without private user media.
        self.original = png_from_rgb(bytes([255, 0, 0]) * 320 * 432)
        metadata = {"upload_id": "original", "mime_type": "image/png", "size_bytes": len(self.original),
                    "sha256": hashlib.sha256(self.original).hexdigest()}
        with ProgramStore(self.database) as store:
            store.bind_device("owner", "board")
            self.intent = store.accept_intent("owner", "board", "first",
                json.dumps({"prompt": "platform test", "media": [metadata]}).encode())["intent_id"]
        self.uploads = {"original": {"data": self.original, "mime_type": "image/png"}}
        self.broker = ProgramBroker(self.database, "owner", self.intent, self.folder / "job", self.uploads)

    def tearDown(self):
        self.temporary.cleanup()

    def call(self, name, args, call_id):
        return self.broker(name, args, call_id, time.monotonic() + 10)

    def run_args(self, source="gfx.begin('#112233');gfx.end();", assets=None):
        return dict(app_id="probe", name="Probe", source=source,
                    requires=["canvas", "input", "time"], asset_refs=assets or [],
                    scenario={"version": 1, "seed": 1, "initial_time_ms": 0, "wall_time": None,
                              "events": [{"type": "frame", "name": "initial"}]})

    def details(self, result):
        return json.loads(result.content[0]["text"])

    def test_real_execution_then_selection_does_not_publish(self):
        result = self.call("run_app", self.run_args(), "run")
        self.assertFalse(result.is_error)
        self.assertEqual(len(result.content), 2)
        self.assertTrue(base64.b64decode(result.content[1]["data"]).startswith(b"\x89PNG"))
        details = self.details(result)
        selected = self.call("submit_app", {"receipt_id": details["receipt_id"]}, "submit")
        self.assertEqual(selected.submission["sha256"], details["package_sha256"])
        with ProgramStore(self.database) as store:
            self.assertIsNone(store.desired_for_device("board"))
            self.assertEqual(store.get_intent("owner", self.intent)["status"], "accepted")
            envelope = store.publish_program("owner", self.intent, selected.submission["receipt_id"],
                                             expected_runner_sha256=details["runner_sha256"])
            self.assertEqual(envelope["manifest"]["sha256"], selected.submission["sha256"])

    def test_duplicate_call_after_restart_returns_exact_receipt_without_execution(self):
        with patch("backend.program_broker.execute_program", wraps=execute_program) as run:
            first = self.call("run_app", self.run_args(), "run")
            self.broker = ProgramBroker(self.database, "owner", self.intent, self.folder / "job", self.uploads)
            second = self.call("run_app", self.run_args(), "run")
            self.assertEqual(run.call_count, 1)
            self.assertEqual(first, second)
            with self.assertRaises(ConflictError):
                self.call("run_app", self.run_args("1+2"), "run")

    def test_interrupted_call_cannot_repeat_a_side_effect(self):
        with patch("backend.program_broker.execute_program", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.call("run_app", self.run_args(), "interrupted")
        with self.assertRaises(ConflictError):
            self.call("run_app", self.run_args(), "interrupted")

    def test_live_missing_scenario_version_gets_actionable_repair(self):
        args = self.run_args()
        del args["scenario"]["version"]
        failed = self.call("run_app", args, "missing-version")
        self.assertTrue(failed.is_error)
        feedback = self.details(failed)
        self.assertIn("version", feedback["required_fields"])
        args["scenario"] = feedback["example"]
        self.assertFalse(self.call("run_app", args, "corrected-version").is_error)
        definition = next(item for item in tool_definitions() if item["name"] == "run_app")
        self.assertIn("version", definition["parameters"]["properties"]["scenario"]["required"])

    def test_original_is_bound_to_frozen_job_and_reference_is_job_scoped(self):
        with self.assertRaises(StoreError):
            ProgramBroker(self.database, "owner", self.intent, self.folder / "bad",
                          {"original": {"data": b"changed", "mime_type": "image/png"}})
        converted = self.call("prepare_uploaded_asset", dict(upload_id="original", asset_id="reference",
                              width=16, height=16, fit="cover"), "asset")
        self.assertFalse(converted.is_error)
        reference = self.details(converted)["asset_ref"]
        result = self.call("run_app", self.run_args("gfx.begin('#000000');gfx.image('reference',0,0);gfx.end();",
                                                    [reference]), "draw")
        self.assertFalse(result.is_error)
        with ProgramStore(self.database) as store:
            raw = store.candidate_bytes("owner", self.intent, self.details(result)["candidate_id"])
            asset = json.loads(raw)["assets"][0]
            self.assertEqual(base64.b64decode(asset["data_b64"]), bytes([255, 0, 0, 255]) * 16 * 16)
        other_job = ProgramBroker(self.database, "owner", self.intent, self.folder / "other-job", self.uploads)
        refused = other_job("run_app", self.run_args(assets=[reference]), "foreign", time.monotonic() + 10)
        self.assertTrue(refused.is_error)

    def test_frame_field_failure_can_be_repaired_from_exact_feedback(self):
        args = self.run_args()
        args["scenario"]["events"][0]["time_ms"] = 0
        rejected = self.call("run_app", args, "bad-frame")
        self.assertTrue(rejected.is_error)
        feedback = self.details(rejected)
        self.assertEqual(feedback["path"], "$.scenario.frame")
        self.assertEqual(set(feedback["required_fields"]), {"type", "name"})
        args["scenario"]["events"][0] = feedback["example"]
        self.assertFalse(self.call("run_app", args, "fixed-frame").is_error)

    def test_failed_execution_and_empty_visuals_cannot_select(self):
        for index, source in enumerate(("throw Error('controlled')", "let state=0;")):
            result = self.call("run_app", self.run_args(source), "fail" + str(index))
            self.assertTrue(result.is_error)
            refused = self.call("submit_app", {"receipt_id": self.details(result)["receipt_id"]}, "select" + str(index))
            self.assertTrue(refused.is_error)
            self.assertIsNone(refused.submission)

    def test_directory_reuse_and_copied_assets_cannot_cross_jobs(self):
        converted = self.call("prepare_uploaded_asset", dict(upload_id="original", asset_id="reference",
                              width=16, height=16, fit="cover"), "asset")
        reference = self.details(converted)["asset_ref"]
        self.call("run_app", self.run_args(), "run")
        original = png_from_rgb(bytes([0, 0, 255]) * 320 * 432)
        uploads = {"original": {"data": original, "mime_type": "image/png"}}
        metadata = {"upload_id": "original", "mime_type": "image/png", "size_bytes": len(original),
                    "sha256": hashlib.sha256(original).hexdigest()}
        with ProgramStore(self.database) as store:
            intent = store.accept_intent("owner", "board", "second",
                json.dumps({"prompt": "different request", "media": [metadata]}).encode())["intent_id"]
        with self.assertRaises(ConflictError):
            ProgramBroker(self.database, "owner", intent, self.folder / "job", uploads)
        broker = ProgramBroker(self.database, "owner", intent, self.folder / "second", uploads)
        record = json.loads((self.folder / "job" / (reference + ".json")).read_bytes())
        for index in range(2):
            if index:
                # Even a copied record rehashed with this job's binding must
                # still correspond to its actual blue original, not old red.
                record["job_binding_sha256"] = broker.binding_hash
            encoded = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
            copied_ref = "asset_" + hashlib.sha256(encoded).hexdigest()
            (broker.folder / (copied_ref + ".json")).write_bytes(encoded)
            refused = broker("run_app", self.run_args(assets=[copied_ref]),
                             "copied" + str(index), time.monotonic() + 10)
            self.assertTrue(refused.is_error)
        fresh = broker("run_app", self.run_args(), "run", time.monotonic() + 10)
        self.assertFalse(fresh.is_error)

    def test_model_receipt_paths_unknown_fields_and_supersession_rejected(self):
        for index, (name, args) in enumerate((
            ("submit_app", {"receipt_id": "receipt_invented"}),
            ("prepare_uploaded_asset", {"upload_id": "/etc/passwd", "asset_id": "test", "width": 1, "height": 1}),
            ("run_app", dict(self.run_args(), command="echo wrong")))):
            self.assertTrue(self.call(name, args, "bad" + str(index)).is_error)
        result = self.call("run_app", self.run_args(), "valid")
        with ProgramStore(self.database) as store:
            store.accept_intent("owner", "board", "second", b'{"prompt":"new","media":[]}')
        with self.assertRaises(ConflictError):
            self.call("submit_app", {"receipt_id": self.details(result)["receipt_id"]}, "stale")


if __name__ == "__main__":
    unittest.main()
