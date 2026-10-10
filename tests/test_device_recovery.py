"""Real SQLite recovery ordering, quarantine and historical ACK invariants."""

import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

from backend.device_recovery import RecoveryStore
from backend.deployments import ConflictError, DeploymentStore, IntegrityError, OwnershipError, StoreError

FIXTURE = (Path(__file__).resolve().parents[1] / "contracts/fixtures/tap-sprint.json").read_bytes()


def identity(envelope):
    return {"deployment_id": envelope["deployment_id"], "sequence": envelope["sequence"],
            **{key: envelope["manifest"][key] for key in ("app_id", "version", "sha256")}}


def acknowledgment(envelope, status="active", device="board"):
    return dict(identity(envelope), device_id=device, status=status)


def report(failed, recovered, seq=1, report_id="report-one", error="runtime_error"):
    return {"protocol_version": 1, "report_id": report_id, "recovery_seq": seq,
            "failed": identity(failed), "recovered": identity(recovered) if recovered else None,
            "error_code": error}


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "store.sqlite"
        self.store = RecoveryStore(self.path)
        self.store.bind_device("owner", "board")
        self.store.bind_device("other", "other-board")
        self.intents = {}
        self.next_key = 0

    def tearDown(self):
        self.store.close()
        self.temporary.cleanup()

    def deployment(self, *, active=True, device="board", session="owner"):
        self.next_key += 1
        intent = self.store.accept_intent(session, device, "request-" + str(self.next_key), b"fixture request")
        envelope = self.store.publish(session, intent["intent_id"], FIXTURE)
        self.intents[envelope["deployment_id"]] = (session, intent["intent_id"])
        if active:
            self.store.record_ack(device, acknowledgment(envelope, device=device))
        return envelope

    def active(self):
        return self.store.active_for_session("owner", "board")

    def history(self, envelope):
        return self.store.ack_history(*self.intents[envelope["deployment_id"]])

    def counts(self):
        return [self.store._db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
                for table in ("recovery_reports", "deployment_quarantine")]

    def test_active_failure_restores_older_identity_and_preserves_historical_ack(self):
        old, failed = self.deployment(), self.deployment()
        before = self.history(failed)
        result = self.store.record_recovery("board", report(failed, old))
        self.assertEqual(result, {"report_id": "report-one", "recovery_seq": 1, "recorded": True, "applied": True})
        self.assertEqual(self.active(), old)
        self.assertIsNone(self.store.desired_for_device("board"))
        self.assertEqual(self.history(failed), before)
        self.assertEqual(self.counts(), [1, 1])

    def test_reboot_confirms_exact_recovered_active_without_crediting_failed_intent(self):
        old, failed = self.deployment(), self.deployment(active=False)
        self.store.record_recovery("board", report(failed, old, error="activation_failed"))
        self.store.close()
        self.store = RecoveryStore(self.path)
        result = self.store.record_ack("board", acknowledgment(old))
        self.assertFalse(result["recorded"])
        self.assertFalse(result["current_success"])
        self.assertTrue(result["active_confirmed"])
        self.assertEqual(self.active(), old)
        self.assertIsNone(self.store.desired_for_device("board"))
        current = self.store._device("board")
        self.assertEqual(current["current_intent_id"], self.intents[failed["deployment_id"]][1])
        self.assertEqual(self.history(failed), [])
        self.assertFalse(self.store.record_ack("board", acknowledgment(failed))["active_confirmed"])
        queued = self.deployment(active=False)
        self.assertTrue(self.store.record_ack("board", acknowledgment(old))["active_confirmed"])
        self.assertEqual(self.store.desired_for_device("board"), queued)
        # A subsequent real failure remains permanent: the confirmation cannot
        # resurrect the app after the durable recovery says it is no longer live.
        self.store.record_recovery("board", report(old, None, 2, "report-two", "activation_failed"))
        rejected = self.store.record_ack("board", acknowledgment(old))
        self.assertFalse(rejected["current_success"])
        self.assertFalse(rejected["active_confirmed"])
        self.assertIsNone(self.active())
        self.assertEqual(self.store.desired_for_device("board"), queued)

    def test_schema2_failure_can_restore_exact_legacy_package_without_its_active_ack(self):
        from tests.test_device_runtime import report as capability_report
        self.store.record_capabilities("board", capability_report())
        old = self.deployment(active=False)
        intent = self.store.accept_intent("owner", "board", "program", b"program request")["intent_id"]
        candidate = self.store.prepare_candidate("owner", intent, app_id="program", name="Program",
            source="gfx.begin('#112233');gfx.end();", assets=[], requires=["canvas"])
        receipt = self.store.record_run("owner", intent, candidate["candidate_id"], runner_sha256="c" * 64,
            scenario=b'{}', result={"scope": "synthetic_storage_receipt_only"}, succeeded=True)
        failed = self.store.publish_program("owner", intent, receipt["receipt_id"], expected_runner_sha256="c" * 64)
        self.assertEqual(failed["manifest"]["schema_version"], 2)
        self.assertTrue(self.store.record_recovery("board", report(failed, old))["applied"])
        self.assertEqual(self.active(), old)
        self.assertEqual(self.history(old), [])
        first_ack = self.store.record_ack("board", acknowledgment(old))
        self.assertTrue(first_ack["recorded"])
        self.assertTrue(first_ack["active_confirmed"])
        self.assertFalse(first_ack["current_success"])

    def test_racing_late_ack_and_recovery_always_finish_on_restored_identity(self):
        old, failed = self.deployment(), self.deployment(active=False)
        barrier = threading.Barrier(2)
        def recover():
            with RecoveryStore(self.path) as store:
                barrier.wait(timeout=2)
                return store.record_recovery("board", report(failed, old))
        def acknowledge():
            with DeploymentStore(self.path) as store:
                barrier.wait(timeout=2)
                return store.record_ack("board", acknowledgment(failed))
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(function) for function in (recover, acknowledge)]
            results = [future.result(timeout=5) for future in futures]
        self.assertTrue(results[0]["applied"])
        self.assertEqual(self.active(), old)
        self.assertIsNone(self.store.desired_for_device("board"))
        self.assertFalse(self.store.record_ack("board", acknowledgment(failed))["current_success"])

    def test_failed_active_ack_missing_supports_no_active_and_already_recovered(self):
        for known_active in (False, True):
            with self.subTest(known_active=known_active):
                if self.counts() != [0, 0]:
                    self.store.close()
                    self.path = Path(self.temporary.name) / "second.sqlite"
                    self.store = RecoveryStore(self.path)
                    self.store.bind_device("owner", "board")
                old = self.deployment(active=known_active)
                failed = self.deployment(active=False)
                self.assertEqual(self.history(failed), [])
                self.assertTrue(self.store.record_recovery("board", report(failed, old))["applied"])
                self.assertEqual(self.active(), old)
                self.assertEqual(self.history(failed), [])

    def test_duplicate_after_restart_is_historical_not_a_new_state_mutation(self):
        old, failed = self.deployment(), self.deployment()
        body = report(failed, old)
        self.store.record_recovery("board", body)
        newer = self.deployment()
        self.store.close()
        self.store = RecoveryStore(self.path)
        reordered = dict(reversed(list(body.items())))
        answer = self.store.record_recovery("board", reordered)
        self.assertFalse(answer["recorded"])
        self.assertTrue(answer["applied"])
        self.assertEqual(self.active(), newer)
        self.assertEqual(self.store.desired_for_device("board"), newer)
        self.assertEqual(self.counts(), [1, 1])
        for changed in (dict(body, error_code="activation_failed"), dict(body, recovery_seq=2),
                        dict(body, report_id="different-id")):
            with self.assertRaises(ConflictError):
                self.store.record_recovery("board", changed)
        self.assertEqual(self.active(), newer)

    def test_reversed_delivery_chain_rejects_gap_then_applies_in_order(self):
        first, second, third = self.deployment(), self.deployment(), self.deployment()
        one = report(third, second)
        two = report(second, first, 2, "report-two")
        with self.assertRaises(ConflictError):
            self.store.record_recovery("board", two)
        self.assertEqual(self.active(), third)
        self.assertEqual(self.counts(), [0, 0])
        self.assertTrue(self.store.record_recovery("board", one)["applied"])
        self.assertEqual(self.active(), second)
        self.assertTrue(self.store.record_recovery("board", two)["applied"])
        self.assertEqual(self.active(), first)
        self.assertEqual(self.counts(), [2, 2])
        self.store.record_recovery("board", one)
        self.assertEqual(self.active(), first)

    def test_newer_desired_preserved_while_failed_current_is_recovered(self):
        old, failed = self.deployment(), self.deployment()
        desired = self.deployment(active=False)
        self.assertTrue(self.store.record_recovery("board", report(failed, old))["applied"])
        self.assertEqual(self.active(), old)
        self.assertEqual(self.store.desired_for_device("board"), desired)

    def test_unrelated_newer_active_never_regresses_but_report_is_acknowledged(self):
        old, failed, newer = self.deployment(), self.deployment(), self.deployment()
        result = self.store.record_recovery("board", report(failed, old))
        self.assertTrue(result["recorded"])
        self.assertFalse(result["applied"])
        self.assertEqual(self.active(), newer)
        self.assertEqual(self.store.desired_for_device("board"), newer)
        self.assertEqual(self.counts(), [1, 1])

    def test_builtin_fallback_clears_only_failed_active_and_desired(self):
        failed = self.deployment()
        self.store.record_recovery("board", report(failed, None, error="recovery_failed"))
        self.assertIsNone(self.active())
        self.assertIsNone(self.store.desired_for_device("board"))

    def test_lost_activation_ack_and_failed_fallback_corrects_older_active_to_builtin(self):
        old = self.deployment()
        failed = self.deployment(active=False)
        self.assertEqual(self.active(), old)
        result = self.store.record_recovery("board", report(failed, None, error="recovery_failed"))
        self.assertTrue(result["applied"])
        self.assertIsNone(self.active())
        self.assertIsNone(self.store.desired_for_device("board"))
        self.assertEqual(self.history(old), [{"status": "active", "error_code": ""}])
        self.assertEqual(self.history(failed), [])

    def test_lost_activation_ack_reconciles_an_unrelated_older_known_active(self):
        first = self.deployment()
        recovered = self.deployment(active=False)
        failed = self.deployment(active=False)
        self.assertEqual(self.active(), first)
        self.assertTrue(self.store.record_recovery("board", report(failed, recovered))["applied"])
        self.assertEqual(self.active(), recovered)

    def test_quarantine_blocks_late_active_even_for_plain_deployment_store(self):
        old, failed = self.deployment(), self.deployment(active=False)
        self.store.record_recovery("board", report(failed, old))
        with DeploymentStore(self.path) as legacy:
            result = legacy.record_ack("board", acknowledgment(failed))
            self.assertTrue(result["recorded"])
            self.assertFalse(result["current_success"])
            self.assertEqual(legacy.active_for_session("owner", "board"), old)
            # Exercise the shared guard, independently of failed/desired clearing.
            legacy._db.execute("UPDATE devices SET desired_id=? WHERE device_id='board'", (failed["deployment_id"],))
            legacy._db.execute("UPDATE deployments SET status='activating' WHERE deployment_id=?", (failed["deployment_id"],))
            self.assertFalse(legacy.record_ack("board", acknowledgment(failed))["current_success"])
            self.assertEqual(legacy.active_for_session("owner", "board"), old)
            # Even inconsistent active metadata cannot bypass permanent quarantine.
            legacy._db.execute("UPDATE devices SET active_id=? WHERE device_id='board'", (failed["deployment_id"],))
            legacy._db.execute("UPDATE deployments SET status='active' WHERE deployment_id=?", (failed["deployment_id"],))
            self.assertFalse(legacy.record_ack("board", acknowledgment(failed))["active_confirmed"])
        self.assertEqual(self.history(failed), [{"status": "active", "error_code": ""}])

    def test_quarantined_target_cannot_be_restored_by_a_new_report(self):
        old, failed = self.deployment(), self.deployment()
        self.store.record_recovery("board", report(failed, old))
        newer = self.deployment()
        with self.assertRaises(IntegrityError):
            self.store.record_recovery("board", report(newer, failed, 2, "report-two"))
        self.assertEqual(self.active(), newer)
        self.assertEqual(self.counts(), [1, 1])

    def test_foreign_and_inexact_identities_are_rejected_atomically(self):
        old, failed = self.deployment(), self.deployment()
        foreign = self.deployment(device="other-board", session="other")
        for body in (report(foreign, old), report(failed, foreign)):
            with self.assertRaises((OwnershipError, IntegrityError)):
                self.store.record_recovery("board", body)
        for which in ("failed", "recovered"):
            for key, value in (("deployment_id", "unknown"), ("sequence", 123), ("app_id", "wrong"),
                               ("version", 123), ("sha256", "b" * 64)):
                body = report(failed, old)
                body[which][key] = value
                with self.subTest(which=which, key=key), self.assertRaises(StoreError):
                    self.store.record_recovery("board", body)
        with self.assertRaises(OwnershipError):
            self.store.record_recovery("unknown-device", report(failed, old))
        for body in (report(failed, failed), report(old, failed)):
            with self.assertRaises(IntegrityError):
                self.store.record_recovery("board", body)
        self.assertEqual(self.active(), failed)
        self.assertEqual(self.counts(), [0, 0])

    def test_strict_fields_types_bounds_and_fixed_errors(self):
        old, failed = self.deployment(), self.deployment()
        base = report(failed, old)
        cases = [dict(base, protocol_version=True), dict(base, protocol_version=2), dict(base, recovery_seq=True),
                 dict(base, recovery_seq=0), dict(base, recovery_seq=2**63), dict(base, report_id="x" * 129),
                 dict(base, error_code="PRIVATE_ERROR"), dict(base, extra=True), dict(base, recovered=[]), None]
        for which in ("failed", "recovered"):
            for key, value in (("version", True), ("sequence", 1.0), ("sha256", "A" * 64),
                               ("app_id", []), ("extra", "unknown")):
                changed = copy.deepcopy(base)
                changed[which][key] = value
                cases.append(changed)
        for body in cases:
            with self.subTest(body=body), self.assertRaises(StoreError):
                self.store.record_recovery("board", body)
        self.assertEqual(self.active(), failed)
        self.assertEqual(self.counts(), [0, 0])

    def test_sql_failure_rolls_back_quarantine_state_and_sequence_together(self):
        old, failed = self.deployment(), self.deployment()
        self.store._db.execute("""CREATE TRIGGER reject_recovery BEFORE INSERT ON recovery_reports
            BEGIN SELECT RAISE(ABORT,'synthetic recovery failure'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.record_recovery("board", report(failed, old))
        self.assertEqual(self.active(), failed)
        self.assertEqual(self.store.desired_for_device("board"), failed)
        self.assertEqual(self.counts(), [0, 0])
        self.store._db.execute("DROP TRIGGER reject_recovery")
        self.assertTrue(self.store.record_recovery("board", report(failed, old))["applied"])


if __name__ == "__main__":
    unittest.main()
