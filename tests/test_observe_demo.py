"""Synthetic job records and real SQLite exercise the read-only observer."""
import contextlib
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.deployments import DeploymentStore
from scripts import observe_demo

ROOT = Path(__file__).absolute().parent.parent
SECRET = "synthetic-private-text-must-never-appear"


class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.jobs = self.directory / "jobs"
        self.jobs.mkdir()
        self.config = {"session_id": "test", "device_id": "board", "session_token": SECRET}
        (self.directory / "demo-config.json").write_text(json.dumps(self.config))
        self.database = self.directory / "deployments.sqlite"
        self.output = self.directory / "evidence/observation.json"
        self.store = DeploymentStore(self.database)
        self.addCleanup(self.store.close)
        self.store.bind_device("test", "board")
        self.now, self.events = 0, []
        self.fixture = (ROOT / "contracts/fixtures/tap-sprint.json").read_bytes()

    def create_job(self, key="first", stage="preparing"):
        intent = self.store.accept_intent("test", "board", key, SECRET.encode())
        self.write_job(intent, stage)
        return intent

    def write_job(self, intent, stage):
        (self.jobs / (intent["intent_id"] + ".json")).write_text(json.dumps(
            {"intent_id": intent["intent_id"], "stage": stage, "detail": SECRET, "prompt": SECRET}))

    def activate(self, envelope):
        manifest = envelope["manifest"]
        self.store.record_ack("board", {"device_id": "board", "deployment_id": envelope["deployment_id"],
                                       "sequence": envelope["sequence"], "app_id": manifest["app_id"],
                                       "version": manifest["version"], "sha256": manifest["sha256"], "status": "active"})

    def run_observer(self, callback):
        def advance(duration):
            self.now += duration
            callback(round(self.now * 4))
        return observe_demo.observe(self.directory, self.output, 2, self.events.append,
                                    clock=lambda: self.now, sleep=advance)

    def test_new_job_requires_real_exact_ack_and_saves_redacted_timing(self):
        state = {}
        def advance(tick):
            if tick == 1:
                state["intent"] = self.create_job()
            elif tick == 2:
                state["deployment"] = self.store.publish("test", state["intent"]["intent_id"], self.fixture)
                self.write_job(state["intent"], "ready")
            elif tick == 3:
                self.activate(state["deployment"])
        report = self.run_observer(advance)
        self.assertEqual(report["result"], "exact_active_ack_observed")
        self.assertEqual([event["stage"] for event in report["events"]], ["preparing", "ready", "active"])
        self.assertEqual([event["elapsed_ms"] for event in report["events"]], [0, 250, 500])
        self.assertEqual(report["events"][-1]["desired"], state["deployment"])
        self.assertEqual(json.loads(self.output.read_text()), report)
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(SECRET, self.output.read_text() + "".join(self.events))

    def test_baseline_active_job_is_excluded_and_cannot_complete_new_job(self):
        old = self.create_job()
        self.activate(self.store.publish("test", old["intent_id"], self.fixture))
        report = self.run_observer(lambda tick: self.create_job("new") if tick == 1 else None)
        self.assertEqual(report["result"], "observation_window_ended")
        self.assertEqual(report["baseline_jobs_excluded"], 1)
        self.assertTrue(report["events"])
        self.assertTrue(all(not event["exact_active_ack_observed"] for event in report["events"]))
        self.assertTrue(all(event["intent_id"] != old["intent_id"] for event in report["events"]))

    def test_superseded_job_with_late_active_ack_is_not_success(self):
        state = {}
        def advance(tick):
            if tick == 1:
                state["intent"] = self.create_job()
                state["deployment"] = self.store.publish("test", state["intent"]["intent_id"], self.fixture)
            elif tick == 2:
                self.create_job("newer")
                self.activate(state["deployment"])
        report = self.run_observer(advance)
        self.assertEqual(report["result"], "observation_window_ended")
        self.assertIn("superseded", [event["stage"] for event in report["events"]])
        self.assertFalse(any(event["exact_active_ack_observed"] for event in report["events"]))

    def test_private_malformed_job_does_not_escape(self):
        def advance(tick):
            if tick == 1:
                self.create_job(stage=SECRET)
                (self.jobs / ("0" * 32 + ".json")).write_text(SECRET)
        report = self.run_observer(advance)
        self.assertEqual(report["events"], [])
        self.assertNotIn(SECRET, self.output.read_text() + "".join(self.events))

    def test_read_only_connection_cannot_mutate_real_database(self):
        with observe_demo.ReadOnlyStore(self.database) as store:
            self.assertIsNone(store.desired_for_device("board"))
            with self.assertRaises(sqlite3.OperationalError):
                store.bind_device("new", "another")
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM devices").fetchone()[0], 1)

    def test_default_does_not_read_private_records_or_create_observer(self):
        with patch.object(observe_demo, "observe", side_effect=AssertionError("must stay inert")):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(observe_demo.main([]), 0)
            self.assertEqual(json.loads(output.getvalue()), {"result": "not_requested"})


if __name__ == "__main__":
    unittest.main()
