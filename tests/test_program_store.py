"""Persistence/ownership tests; synthetic receipts do not prove native execution."""

import json
from pathlib import Path
import tempfile
import unittest

from backend.deployments import ConflictError, DeploymentStore, IntegrityError, OwnershipError, StoreError
from backend.program_store import ProgramStore

RUNNER = "a" * 64


class ProgramStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "store.sqlite"
        self.store = ProgramStore(self.path)
        self.store.bind_device("owner", "board")
        self.store.bind_device("other", "another")
        self.intent = self.intent_for("first")

    def tearDown(self):
        self.store.close()
        self.temporary.cleanup()

    def intent_for(self, key):
        return self.store.accept_intent("owner", "board", key, b'{"prompt":"probe"}')["intent_id"]

    def candidate(self, source="let value = 1 + 2;", intent=None):
        return self.store.prepare_candidate("owner", intent or self.intent, app_id="probe", name="Probe",
                                            source=source, assets=[], requires=["canvas"])

    def receipt(self, candidate, *, intent=None, succeeded=True):
        return self.store.record_run("owner", intent or self.intent, candidate["candidate_id"],
                                     runner_sha256=RUNNER, scenario=b'{"version":1}',
                                     result={"test_scope": "synthetic_record_only"}, succeeded=succeeded)["receipt_id"]

    def publish(self, receipt, intent=None, runner=RUNNER):
        return self.store.publish_program("owner", intent or self.intent, receipt, expected_runner_sha256=runner)

    def test_publication_is_exact_pretested_bytes_and_idempotent_after_restart(self):
        candidate = self.candidate()
        body = self.store.candidate_bytes("owner", self.intent, candidate["candidate_id"])
        receipt = self.receipt(candidate)
        self.store.close()
        self.store = ProgramStore(self.path)
        envelope = self.publish(receipt)
        self.assertEqual(self.store.package_for_device("board", envelope["deployment_id"]), body)
        self.assertEqual(envelope["manifest"]["version"], candidate["version"])
        self.assertEqual(envelope["manifest"]["sha256"], candidate["sha256"])
        self.assertEqual(envelope["manifest"]["min_runtime_version"], "0.3.0")
        self.assertEqual(self.publish(receipt), envelope)

    def test_repair_retains_reserved_version_but_invalidates_byte_identity(self):
        first, second = self.candidate(), self.candidate("let value = 4;")
        self.assertEqual(first["version"], second["version"])
        self.assertNotEqual(first["sha256"], second["sha256"])
        self.assertEqual(self.candidate(), first)
        first_receipt, second_receipt = self.receipt(first), self.receipt(second)
        self.publish(second_receipt)
        with self.assertRaises(ConflictError):
            self.publish(first_receipt)

    def test_unknown_foreign_and_failed_receipts_cannot_publish(self):
        candidate = self.candidate()
        with self.assertRaises(OwnershipError):
            self.publish("receipt_model_printed_success")
        with self.assertRaises(IntegrityError):
            self.publish(self.receipt(candidate, succeeded=False))
        foreign_intent = self.store.accept_intent("other", "another", "foreign", b"request")["intent_id"]
        receipt = self.receipt(candidate)
        with self.assertRaises(OwnershipError):
            self.store.publish_program("other", foreign_intent, receipt, expected_runner_sha256=RUNNER)
        with self.assertRaises(OwnershipError):
            self.store.candidate_bytes("other", foreign_intent, candidate["candidate_id"])
        self.assertIsNone(self.store.desired_for_device("board"))

    def test_superseded_intent_cannot_record_run_or_publish(self):
        candidate = self.candidate()
        receipt = self.receipt(candidate)
        newer = self.intent_for("second")
        for call in (lambda: self.receipt(candidate), lambda: self.publish(receipt)):
            with self.assertRaises(ConflictError):
                call()
        new_candidate = self.candidate(intent=newer)
        self.assertGreater(new_candidate["version"], candidate["version"])

    def test_candidate_tampering_is_detected_before_receipt_or_publish(self):
        candidate = self.candidate()
        receipt = self.receipt(candidate)
        body = self.store.candidate_bytes("owner", self.intent, candidate["candidate_id"])
        tampered = body.replace(b"1 + 2", b"5 + 6")
        self.assertNotEqual(tampered, body)
        self.store._db.execute("UPDATE program_candidates SET body=?", (tampered,))
        with self.assertRaises(IntegrityError):
            self.publish(receipt)

    def test_scenario_and_runner_mismatch_reject_receipt(self):
        receipt = self.receipt(self.candidate())
        with self.assertRaises(IntegrityError):
            self.publish(receipt, runner="b" * 64)
        self.store._db.execute("UPDATE program_runs SET scenario=?", (b"different",))
        with self.assertRaises(IntegrityError):
            self.publish(receipt)

    def test_legacy_and_program_versions_do_not_collide(self):
        first = self.candidate()
        newer = self.intent_for("legacy")
        fixture = Path(__file__).resolve().parents[1] / "contracts/fixtures/tap-sprint.json"
        app = json.loads(fixture.read_text())
        app["app_id"] = "probe"
        legacy = self.store.publish("owner", newer, json.dumps(app).encode())
        self.assertGreater(legacy["manifest"]["version"], first["version"])
        third_intent = self.intent_for("third")
        third = self.candidate(intent=third_intent)
        self.assertGreater(third["version"], legacy["manifest"]["version"])

    def test_legacy_publication_cannot_bypass_program_receipt(self):
        candidate = self.candidate()
        body = self.store.candidate_bytes("owner", self.intent, candidate["candidate_id"])
        with self.assertRaises(StoreError):
            self.store.publish("owner", self.intent, body)

    def test_separate_legacy_connection_honors_unpublished_program_reservation(self):
        with DeploymentStore(self.path) as legacy:
            legacy.bind_device("owner", "second_board")
            candidate = self.candidate()
            receipt = self.receipt(candidate)
            intent = legacy.accept_intent("owner", "second_board", "mixed", b"request")["intent_id"]
            fixture = Path(__file__).resolve().parents[1] / "contracts/fixtures/tap-sprint.json"
            app = json.loads(fixture.read_text())
            app["app_id"] = "probe"
            envelope = legacy.publish("owner", intent, json.dumps(app).encode())
            self.assertEqual(envelope["manifest"]["version"], candidate["version"] + 1)
            published = self.publish(receipt)
            self.assertEqual(published["manifest"]["version"], candidate["version"])
            self.assertEqual(published["manifest"]["sha256"], candidate["sha256"])

    def test_bad_candidate_does_not_consume_version_reservation(self):
        for identifier in (["wrong_type"], "../escape", "Uppercase"):
            with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                self.store.prepare_candidate("owner", self.intent, app_id=identifier, name="Probe",
                                             source="1", assets=[], requires=[])
        self.assertEqual(self.store._db.execute("SELECT COUNT(*) FROM program_versions").fetchone()[0], 0)
        self.assertEqual(self.candidate()["version"], 1)


if __name__ == "__main__":
    unittest.main()
