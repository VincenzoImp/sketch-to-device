"""Replay uses synthetic private inputs and real read-only SQLite state."""
import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from backend.deployments import DeploymentStore
from scripts import replay_generation

ROOT = Path(__file__).absolute().parent.parent
SECRET = "synthetic-private-prompt-and-provider-error"
FIXTURE = (ROOT / "contracts/fixtures/tap-sprint.json").read_bytes()


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / "service"
        self.output = Path(self.temp.name) / "artifacts"
        self.directory.mkdir()
        (self.directory / "uploads").mkdir()
        (self.directory / "demo-config.json").write_text(json.dumps(
            {"session_id": "demo", "device_id": "board", "session_token": SECRET}))
        self.store = DeploymentStore(self.directory / "deployments.sqlite")
        self.addCleanup(self.store.close)
        self.store.bind_device("demo", "board")
        self.upload = self.directory / "uploads" / ("a" * 32)
        self.media = b"synthetic exact original media bytes"
        self.upload.write_bytes(self.media)
        self.snapshot = {"prompt": SECRET, "media": [
            {"upload_id": self.upload.name, "mime_type": "audio/webm", "size_bytes": len(self.media),
             "sha256": hashlib.sha256(self.media).hexdigest()}]}
        self.events = []

    def failed(self, key="first", snapshot=None):
        request = json.dumps(snapshot or self.snapshot).encode()
        intent = self.store.accept_intent("demo", "board", key, request)
        self.store.fail_intent("demo", intent["intent_id"], "provider_response")
        return intent

    def run_replay(self, generator):
        return replay_generation.replay(self.directory, self.output, generator, self.events.append)

    def test_exact_latest_frozen_input_and_no_service_mutation(self):
        self.failed("old", {"prompt": "Older request", "media": []})
        self.failed()
        # Mutable upload metadata is deliberately inconsistent; the frozen record owns the input.
        (self.directory / "uploads" / (self.upload.name + ".json")).write_text(json.dumps({"prompt": SECRET}))
        before = list(self.store._db.iterdump())
        def generate(prompt, media, progress):
            self.assertEqual(prompt, SECRET)
            self.assertEqual(len(media), 1)
            self.assertEqual(media[0]["mime_type"], "audio/webm")
            self.assertEqual(media[0]["path"].read_bytes(), self.media)
            self.assertNotEqual(media[0]["path"], self.upload)
            self.assertEqual(media[0]["path"].stat().st_mode & 0o777, 0o600)
            progress("generating", SECRET)
            progress(SECRET, SECRET)
            return FIXTURE
        report = self.run_replay(generate)
        self.assertEqual(report["result"], "replayed_and_host_validated")
        self.assertEqual(report["sha256"], hashlib.sha256(FIXTURE).hexdigest())
        self.assertEqual((self.output / "replayed-app.json").read_bytes(), FIXTURE)
        self.assertEqual((self.output / "replayed-app.json").stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads((self.output / "replay-last-result.json").read_text()), report)
        self.assertEqual(list(self.store._db.iterdump()), before)
        self.assertEqual(self.upload.read_bytes(), self.media)
        self.assertFalse(report["device_installed"])
        self.assertNotIn(SECRET, "".join(self.events))

    def test_tampered_original_media_rejected_before_generator(self):
        self.failed()
        self.upload.write_bytes(b"changed")
        generator = Mock(side_effect=AssertionError("must not call providers"))
        report = self.run_replay(generator)
        self.assertEqual(report["code"], "replay_input_invalid")
        generator.assert_not_called()
        self.assertFalse((self.output / "replayed-app.json").exists())

    def test_invalid_frozen_path_rejected_before_generator(self):
        self.snapshot["media"][0]["upload_id"] = "../../demo-config.json"
        self.failed()
        generator = Mock(side_effect=AssertionError("must not call providers"))
        report = self.run_replay(generator)
        self.assertEqual(report["code"], "replay_input_invalid")
        generator.assert_not_called()

    def test_failure_diagnostics_are_filtered_without_provider_text(self):
        self.failed()
        failure = RuntimeError(SECRET)
        failure.code = "provider_response"
        failure.diagnostics = {"phase": "poll", "reason": "interaction_not_completed",
                               "interaction_status": "incomplete", "elapsed_ms": 82500,
                               "usage": {"total_tokens": 32780, "total_input_tokens": SECRET},
                               "prompt": SECRET, "message": SECRET, "metadata": {"key": SECRET}}
        def generate(*_):
            raise failure
        report = self.run_replay(generate)
        self.assertEqual(report["code"], "provider_response")
        self.assertEqual(report["diagnostics"], {"phase": "poll", "reason": "interaction_not_completed",
                                                  "interaction_status": "incomplete", "elapsed_ms": 82500,
                                                  "usage": {"total_tokens": 32780}})
        self.assertNotIn(SECRET, "".join(self.events) + (self.output / "replay-last-result.json").read_text())
        self.assertFalse((self.output / "replayed-app.json").exists())

    def test_active_generation_is_preserved_and_not_replayed(self):
        self.failed()
        active = self.store.accept_intent("demo", "board", "busy", b"new job")
        generator = Mock(side_effect=AssertionError("must not call providers"))
        report = self.run_replay(generator)
        self.assertEqual(report["code"], "generation_busy")
        generator.assert_not_called()
        self.assertEqual(self.store.get_intent("demo", active["intent_id"])["status"], "accepted")

    def test_newer_fixture_records_are_skipped_and_desired_fixture_is_preserved(self):
        self.failed()
        fixture_intent = self.store.accept_intent("demo", "board", "failed-fixture",
                                                 b'{"kind":"hardware_fixture","fixture":"tap-sprint"}')
        self.store.fail_intent("demo", fixture_intent["intent_id"], "fixture_error")
        current = self.store.accept_intent("demo", "board", "current-fixture",
                                          b'{"kind":"hardware_fixture","fixture":"focus-timer"}')
        desired = self.store.publish("demo", current["intent_id"], FIXTURE)
        before = list(self.store._db.iterdump())
        def generate(prompt, media, _progress):
            self.assertEqual(prompt, SECRET)
            self.assertEqual(media[0]["path"].read_bytes(), self.media)
            return FIXTURE
        report = self.run_replay(generate)
        self.assertEqual(report["result"], "replayed_and_host_validated")
        self.assertEqual(self.store.desired_for_device("board"), desired)
        self.assertEqual(self.store.get_intent("demo", current["intent_id"])["status"], "published")
        self.assertEqual(list(self.store._db.iterdump()), before)

    def test_default_and_selection_without_live_are_inert(self):
        for args in ([], ["--last-failed"]):
            with patch.object(replay_generation, "replay", side_effect=AssertionError("must stay inert")):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(replay_generation.main(args), 0)
                self.assertEqual(json.loads(output.getvalue()), {"result": "live_not_requested"})


if __name__ == "__main__":
    unittest.main()
