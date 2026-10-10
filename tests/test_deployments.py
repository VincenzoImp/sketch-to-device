"""Real temporary SQLite checks; fixtures are not generated/provider evidence."""

import hashlib
import json
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from backend.deployments import (
    ConflictError, DeploymentStore, IntegrityError, OwnershipError, StoreError,
)
from runtime.validation import ValidationError, package_report, parse_app


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = (ROOT / "contracts/fixtures/tap-sprint.json").read_bytes()


def changed_artifact(name="New Game"):
    app = json.loads(ARTIFACT)
    app["name"] = name
    app["version"] = 999
    return json.dumps(app).encode("utf-8")


def acknowledgment(envelope, status="active", device="device_one"):
    manifest = envelope["manifest"]
    return {"device_id": device, "deployment_id": envelope["deployment_id"],
            "sequence": envelope["sequence"], "app_id": manifest["app_id"],
            "version": manifest["version"], "sha256": manifest["sha256"],
            "status": status}


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "deployments.sqlite"
        self.store = DeploymentStore(self.path)
        self.store.bind_device("session_one", "device_one")

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def intent(self, key="request_one", body=b"new game"):
        return self.store.accept_intent("session_one", "device_one", key, body)

    def publish(self, intent=None, artifact=ARTIFACT):
        intent = self.intent() if intent is None else intent
        return self.store.publish("session_one", intent["intent_id"], artifact)

    def establish_active(self):
        deployment = self.publish()
        result = self.store.record_ack("device_one", acknowledgment(deployment))
        self.assertTrue(result["current_success"])
        return deployment

    def count(self, table):
        with sqlite3.connect(str(self.path)) as connection:
            return connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]

    def test_exact_request_idempotency_survives_reopen(self):
        first = self.intent()
        self.store.close()
        self.store = DeploymentStore(self.path)
        self.assertEqual(self.intent(), first)
        self.assertEqual(self.count("intents"), 1)
        self.assertEqual(self.intent("request_two")["sequence"], 2)
        self.assertEqual(self.intent()["intent_id"], first["intent_id"])
        self.assertIsNone(self.store.desired_for_device("device_one"))

    def test_changed_request_or_target_conflicts_with_same_key(self):
        self.intent()
        with self.assertRaises(ConflictError):
            self.intent(body=b"new game ")
        self.store.bind_device("session_one", "device_two")
        with self.assertRaises(ConflictError):
            self.store.accept_intent("session_one", "device_two", "request_one", b"new game")
        self.assertEqual(self.count("intents"), 1)

    def test_session_ownership_for_accept_publish_read_and_failure(self):
        intent = self.intent()
        for operation in (
            lambda: self.store.accept_intent("intruder", "device_one", "other", b"request"),
            lambda: self.store.publish("intruder", intent["intent_id"], ARTIFACT),
            lambda: self.store.get_intent("intruder", intent["intent_id"]),
            lambda: self.store.fail_intent("intruder", intent["intent_id"], "test_error"),
            lambda: self.store.active_for_session("intruder", "device_one"),
            lambda: self.store.ack_history("intruder", intent["intent_id"]),
        ):
            with self.subTest(operation=operation):
                with self.assertRaises(OwnershipError):
                    operation()

    def test_backend_version_assignment_and_exact_final_bytes(self):
        original = changed_artifact()
        deployment = self.publish(artifact=original)
        body = self.store.package_for_device("device_one", deployment["deployment_id"])
        report = package_report(body)
        self.assertEqual(parse_app(body)["version"], 1)
        self.assertEqual(parse_app(body)["name"], "New Game")
        for key in ("app_id", "version", "schema_version", "size_bytes", "sha256"):
            self.assertEqual(deployment["manifest"][key], report[key])
        with sqlite3.connect(str(self.path)) as connection:
            source, served = connection.execute("SELECT source_sha256,sha256 FROM deployments").fetchone()
        self.assertEqual(source, hashlib.sha256(original).hexdigest())
        self.assertNotEqual(source, served)
        second = self.publish(self.intent("request_two"), ARTIFACT)
        self.assertEqual(second["manifest"]["version"], 2)

    def test_absent_or_wrong_type_identity_never_bypasses_ownership(self):
        self.establish_active()
        for identity in (None, False, 1, ""):
            with self.subTest(identity=identity):
                with self.assertRaises(StoreError):
                    self.store.active_for_session(identity, "device_one")
                with self.assertRaises(StoreError):
                    self.store.desired_for_device(identity)

    def test_republish_idempotent_only_for_same_original_artifact(self):
        intent = self.intent()
        first = self.publish(intent)
        self.assertEqual(self.publish(intent), first)
        with self.assertRaises(ConflictError):
            self.publish(intent, ARTIFACT + b" ")
        self.assertEqual(self.count("deployments"), 1)
        self.assertEqual(self.store.desired_for_device("device_one"), first)

    def test_new_intent_revokes_queued_package_and_preserves_active(self):
        active = self.establish_active()
        queued_intent = self.intent("request_two")
        queued = self.publish(queued_intent)
        newest = self.intent("request_three")
        self.assertIsNone(self.store.desired_for_device("device_one"))
        self.assertEqual(self.store.active_for_session("session_one", "device_one"), active)
        with self.assertRaises(OwnershipError):
            self.store.package_for_device("device_one", queued["deployment_id"])
        with self.assertRaises(ConflictError):
            self.publish(queued_intent)
        old_ack = self.store.record_ack("device_one", acknowledgment(queued))
        self.assertFalse(old_ack["current_success"])
        self.assertEqual(self.store.ack_history("session_one", queued_intent["intent_id"]),
                         [{"status": "active", "error_code": ""}])
        self.assertEqual(self.store.active_for_session("session_one", "device_one"), active)
        self.store.fail_intent("session_one", newest["intent_id"], "generation_failed")
        self.assertEqual(self.store.active_for_session("session_one", "device_one"), active)
        self.assertIsNone(self.store.desired_for_device("device_one"))

    def test_old_ack_after_new_publication_cannot_complete_new_deployment(self):
        old_intent = self.intent()
        old = self.publish(old_intent)
        new = self.publish(self.intent("request_two"))
        outcome = self.store.record_ack("device_one", acknowledgment(old))
        self.assertFalse(outcome["current_success"])
        self.assertFalse(outcome["active_confirmed"])
        self.assertIsNone(self.store.active_for_session("session_one", "device_one"))
        self.assertEqual(self.store.desired_for_device("device_one"), new)
        self.assertTrue(self.store.record_ack("device_one", acknowledgment(new))["current_success"])
        self.store.record_ack("device_one", acknowledgment(old))
        self.assertEqual(self.store.active_for_session("session_one", "device_one"), new)

    def test_retained_active_confirmation_does_not_complete_newer_intent(self):
        active = self.establish_active()
        new_intent = self.intent("request_two")
        new = self.publish(new_intent)
        answer = self.store.record_ack("device_one", acknowledgment(active))
        self.assertFalse(answer["current_success"])
        self.assertTrue(answer["active_confirmed"])
        self.assertEqual(self.store.desired_for_device("device_one"), new)
        self.assertEqual(self.store.active_for_session("session_one", "device_one"), active)
        self.assertFalse(self.store.record_ack("device_one", acknowledgment(active, "activating"))["active_confirmed"])
        current = self.store.record_ack("device_one", acknowledgment(new))
        self.assertTrue(current["current_success"])
        self.assertTrue(current["active_confirmed"])
        self.assertFalse(self.store.record_ack("device_one", acknowledgment(active))["active_confirmed"])

    def test_rebound_previous_session_active_is_not_confirmed(self):
        active = self.establish_active()
        self.store.bind_device("session_two", "device_one")
        answer = self.store.record_ack("device_one", acknowledgment(active))
        self.assertFalse(answer["current_success"])
        self.assertFalse(answer["active_confirmed"])

    def test_active_confirmation_requires_active_ack_preserving_legacy_success_meaning(self):
        active = self.establish_active()
        late_failure = acknowledgment(active, "failed")
        late_failure["error_code"] = "historical_failure"
        answer = self.store.record_ack("device_one", late_failure)
        # Legacy current_success describes the current deployment state, even
        # for a late non-active receipt. The new field confirms active ACKs only.
        self.assertTrue(answer["current_success"])
        self.assertFalse(answer["active_confirmed"])
        self.assertEqual(self.store.active_for_session("session_one", "device_one"), active)

    def test_invalid_app_never_publishes_or_changes_active(self):
        active = self.establish_active()
        intent = self.intent("request_two")
        invalid = json.loads(ARTIFACT)
        invalid["screens"][0]["widgets"][0]["script"] = "unsupported"
        with self.assertRaises(ValidationError):
            self.publish(intent, json.dumps(invalid).encode())
        self.assertEqual(self.count("deployments"), 1)
        self.assertEqual(self.store.active_for_session("session_one", "device_one"), active)
        self.assertIsNone(self.store.desired_for_device("device_one"))
        self.assertEqual(self.publish(intent)["manifest"]["version"], 2)

    def test_rebinding_revokes_old_intent_and_rechecks_owner(self):
        intent = self.intent()
        old = self.publish(intent)
        self.store.bind_device("session_two", "device_one")
        self.assertIsNone(self.store.desired_for_device("device_one"))
        with self.assertRaises(OwnershipError):
            self.publish(intent)
        self.assertFalse(self.store.record_ack("device_one", acknowledgment(old))["current_success"])
        new = self.store.accept_intent("session_two", "device_one", "new_key", b"new owner")
        self.assertGreater(new["sequence"], intent["sequence"])

    def test_download_and_ack_reject_another_device(self):
        deployment = self.publish()
        self.store.bind_device("session_two", "device_two")
        with self.assertRaises(OwnershipError):
            self.store.package_for_device("device_two", deployment["deployment_id"])
        with self.assertRaises(OwnershipError):
            self.store.record_ack("device_two", acknowledgment(deployment))
        with self.assertRaises(OwnershipError):
            self.store.record_ack("device_two", acknowledgment(deployment, device="device_two"))
        self.assertEqual(self.count("acknowledgments"), 0)

    def test_ack_requires_complete_exact_identity(self):
        deployment = self.publish()
        for key, value in (("sequence", 99), ("version", 99), ("app_id", "different"),
                           ("sha256", "0" * 64), ("device_id", "device_other")):
            ack = acknowledgment(deployment)
            ack[key] = value
            with self.subTest(key=key):
                with self.assertRaises((IntegrityError, OwnershipError)):
                    self.store.record_ack("device_one", ack)
        for key in acknowledgment(deployment):
            ack = acknowledgment(deployment)
            del ack[key]
            with self.subTest(missing=key):
                with self.assertRaises(StoreError):
                    self.store.record_ack("device_one", ack)
        self.assertEqual(self.count("acknowledgments"), 0)
        self.assertIsNone(self.store.active_for_session("session_one", "device_one"))

    def test_malformed_ack_values_raise_controlled_errors(self):
        deployment = self.publish()
        for key, value in (("sequence", True), ("version", True), ("status", []),
                           ("sha256", None), ("error_code", None), ("unexpected", "field")):
            ack = acknowledgment(deployment)
            ack[key] = value
            with self.subTest(key=key):
                with self.assertRaises(StoreError):
                    self.store.record_ack("device_one", ack)

    def test_duplicate_active_ack_and_late_progress_are_idempotent(self):
        intent = self.intent()
        deployment = self.publish(intent)
        first = self.store.record_ack("device_one", acknowledgment(deployment))
        duplicate = self.store.record_ack("device_one", acknowledgment(deployment))
        self.assertTrue(first["recorded"])
        self.assertFalse(duplicate["recorded"])
        self.assertTrue(duplicate["current_success"])
        self.store.record_ack("device_one", acknowledgment(deployment, "downloading"))
        self.assertEqual(self.store.active_for_session("session_one", "device_one"), deployment)
        self.store.close()
        self.store = DeploymentStore(self.path)
        self.assertEqual(self.store.desired_for_device("device_one"), deployment)
        self.assertEqual(self.store.active_for_session("session_one", "device_one"), deployment)
        self.assertFalse(self.store.record_ack("device_one", acknowledgment(deployment))["recorded"])

    def test_failed_device_install_preserves_previous_active(self):
        active = self.establish_active()
        new = self.publish(self.intent("request_two"))
        ack = acknowledgment(new, "failed")
        ack["error_code"] = "invalid_package"
        self.assertFalse(self.store.record_ack("device_one", ack)["current_success"])
        self.assertIsNone(self.store.desired_for_device("device_one"))
        self.assertEqual(self.store.active_for_session("session_one", "device_one"), active)
        self.assertFalse(self.store.record_ack("device_one", acknowledgment(new))["current_success"])

    def test_tampered_body_hash_size_and_identity_are_rejected(self):
        deployment = self.publish()
        for column, bad in (("body", b"{}"), ("sha256", "0" * 64), ("size_bytes", 1),
                            ("app_id", "different"), ("version", 90), ("sequence", 90),
                            ("device_id", "different")):
            with self.subTest(column=column):
                with sqlite3.connect(str(self.path)) as connection:
                    original = connection.execute("SELECT " + column + " FROM deployments").fetchone()[0]
                    connection.execute("UPDATE deployments SET " + column + "=?", (bad,))
                with self.assertRaises(IntegrityError):
                    self.store.desired_for_device("device_one")
                with self.assertRaises(IntegrityError):
                    self.store.package_for_device("device_one", deployment["deployment_id"])
                with sqlite3.connect(str(self.path)) as connection:
                    connection.execute("UPDATE deployments SET " + column + "=?", (original,))

    def test_sql_failure_rolls_back_body_manifest_and_publication_together(self):
        intent = self.intent()
        with sqlite3.connect(str(self.path)) as connection:
            connection.execute("""CREATE TRIGGER reject_publish BEFORE UPDATE OF desired_id ON devices
                                  WHEN NEW.desired_id IS NOT NULL BEGIN
                                  SELECT RAISE(ABORT, 'synthetic write failure'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.publish(intent)
        self.assertEqual(self.count("deployments"), 0)
        self.assertIsNone(self.store.desired_for_device("device_one"))
        self.assertEqual(self.store.get_intent("session_one", intent["intent_id"])["status"], "accepted")
        with sqlite3.connect(str(self.path)) as connection:
            connection.execute("DROP TRIGGER reject_publish")
        self.assertEqual(self.publish(intent)["manifest"]["version"], 1)

    def run_race(self, left, right):
        barrier = threading.Barrier(2)

        def worker(operation):
            with DeploymentStore(self.path) as store:
                barrier.wait(timeout=5)
                return operation(store)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker, operation) for operation in (left, right)]
            return [future.result(timeout=10) for future in futures]

    def test_two_racing_requests_share_idempotent_intent(self):
        create = lambda store: store.accept_intent("session_one", "device_one", "same", b"snapshot")
        left, right = self.run_race(create, create)
        self.assertEqual(left["intent_id"], right["intent_id"])
        self.assertEqual(left["sequence"], 1)
        self.assertEqual(self.count("intents"), 1)

    def test_two_racing_distinct_intents_get_monotonic_sequences(self):
        results = self.run_race(
            lambda store: store.accept_intent("session_one", "device_one", "left", b"left"),
            lambda store: store.accept_intent("session_one", "device_one", "right", b"right"))
        older, newer = sorted(results, key=lambda row: row["sequence"])
        self.assertEqual([older["sequence"], newer["sequence"]], [1, 2])
        with self.assertRaises(ConflictError):
            self.publish(older)
        self.assertEqual(self.publish(newer)["sequence"], 2)

    def test_racing_accept_and_old_publish_never_leave_old_desired(self):
        active = self.establish_active()
        older = self.intent("request_two")

        def publish_old(store):
            try:
                return store.publish("session_one", older["intent_id"], ARTIFACT)
            except ConflictError:
                return None

        _, newer = self.run_race(publish_old, lambda store: store.accept_intent(
            "session_one", "device_one", "request_three", b"newest"))
        self.assertEqual(newer["sequence"], 3)
        self.assertIsNone(self.store.desired_for_device("device_one"))
        self.assertEqual(self.store.active_for_session("session_one", "device_one"), active)

    def test_racing_publications_share_one_deployment_and_version(self):
        intent = self.intent()
        publish = lambda store: store.publish("session_one", intent["intent_id"], ARTIFACT)
        left, right = self.run_race(publish, publish)
        self.assertEqual(left, right)
        self.assertEqual(self.count("deployments"), 1)
        self.assertEqual(left["manifest"]["version"], 1)

    def test_fixture_racing_phone_cannot_supersede_inflight_generation(self):
        def fixture(store):
            try:
                return store.accept_intent("session_one", "device_one", "fixture", b"fixture", require_idle=True)
            except ConflictError:
                return None

        _, phone = self.run_race(fixture, lambda store: store.accept_intent(
            "session_one", "device_one", "phone", b"phone request"))
        self.assertEqual(self.store.get_intent("session_one", phone["intent_id"])["status"], "accepted")
        with self.assertRaises(ConflictError):
            self.store.accept_intent("session_one", "device_one", "another_fixture", b"fixture", require_idle=True)
        self.assertIsNone(self.store.desired_for_device("device_one"))


if __name__ == "__main__":
    unittest.main()
