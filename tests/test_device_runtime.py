"""Real SQLite capability gates; declarations are not physical attestation."""

import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from backend.device_runtime import CapabilityError, DeviceRuntimeStore, PROFILE
from backend.deployments import ConflictError, DeploymentStore, IntegrityError, OwnershipError, StoreError


def report(**changes):
    value = {"protocol_version": 1, "device_id": "board", "boot_id": "boot-one",
             "runtime_version": PROFILE["runtime_version"], "schema_versions": [1, 2],
             "engine": PROFILE["engine"], "sdk": PROFILE["sdk"], "profile": PROFILE["profile"],
             "modules": list(PROFILE["modules"]), "viewport": dict(PROFILE["viewport"]),
             "firmware_elf_sha256": "a" * 64}
    value.update(changes)
    return value


class DeviceRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "store.sqlite"
        self.store = DeviceRuntimeStore(self.path)
        self.store.bind_device("owner", "board")
        self.store.bind_device("other", "other-board")

    def tearDown(self):
        self.store.close()
        self.temporary.cleanup()

    def target(self, **kwargs):
        return self.store.program_target("owner", "board", **kwargs)

    def assert_gate(self, code, **kwargs):
        with self.assertRaises(CapabilityError) as caught:
            self.target(**kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_fresh_report_persists_across_connections_and_has_exact_boundaries(self):
        self.assert_gate("capabilities_missing", now=100)
        self.store.record_capabilities("board", report(), now=100)
        self.store.close()
        self.store = DeviceRuntimeStore(self.path)
        self.assertEqual(self.target(now=100)["age_seconds"], 0)
        self.assertEqual(self.target(now=130)["age_seconds"], 30)
        self.assert_gate("capabilities_stale", now=130.001)
        self.assert_gate("capabilities_stale", now=99.999)
        self.assert_gate("capabilities_stale", now=111, max_age=10)
        with self.assertRaises(StoreError):
            self.target(now=131, max_age=31)

    def test_real_server_clock_is_evaluated_for_each_call(self):
        with patch("backend.device_runtime.time.time", return_value=100):
            self.store.record_capabilities("board", report())
            self.assertEqual(self.target()["received_at"], 100)
        with patch("backend.device_runtime.time.time", return_value=131):
            self.assert_gate("capabilities_stale")

    def test_accept_publish_and_download_each_enforce_current_capability_atomically(self):
        with self.assertRaises(CapabilityError):
            self.store.accept_program_intent("owner", "board", "one", b"request")
        self.assertEqual(self.store._db.execute("SELECT COUNT(*) FROM intents").fetchone()[0], 0)
        with patch("backend.device_runtime.time.time", return_value=100):
            self.store.record_capabilities("board", report())
            intent = self.store.accept_program_intent("owner", "board", "one", b"request")["intent_id"]
        candidate = self.store.prepare_candidate("owner", intent, app_id="probe", name="Probe",
            source="gfx.begin('#000000');gfx.end();", assets=[], requires=["canvas"])
        receipt = self.store.record_run("owner", intent, candidate["candidate_id"], runner_sha256="a" * 64,
            scenario=b'{}', result={"scope": "synthetic_store_receipt"}, succeeded=True)
        with patch("backend.device_runtime.time.time", return_value=131), self.assertRaises(CapabilityError):
            self.store.publish_program("owner", intent, receipt["receipt_id"], expected_runner_sha256="a" * 64)
        self.assertIsNone(self.store.desired_for_device("board"))
        self.assertEqual(self.store.get_intent("owner", intent)["status"], "accepted")
        with patch("backend.device_runtime.time.time", return_value=132):
            self.store.record_capabilities("board", report())
            envelope = self.store.publish_program("owner", intent, receipt["receipt_id"], expected_runner_sha256="a" * 64)
            raw = self.store.package_for_device("board", envelope["deployment_id"])
            self.assertEqual(raw, self.store._db.execute("SELECT body FROM program_candidates").fetchone()[0])
        with patch("backend.device_runtime.time.time", return_value=163), self.assertRaises(CapabilityError):
            self.store.package_for_device("board", envelope["deployment_id"])
        self.assertEqual(self.store.desired_for_device("board"), envelope)

    def test_foreign_unknown_device_and_foreign_session_cannot_use_report(self):
        with self.assertRaises(OwnershipError):
            self.store.record_capabilities("board", report(device_id="other-board"), now=100)
        with self.assertRaises(OwnershipError):
            self.store.record_capabilities("missing", report(device_id="missing"), now=100)
        self.store.record_capabilities("board", report(), now=100)
        with self.assertRaises(OwnershipError):
            self.store.program_target("other", "board", now=100)
        self.store.bind_device("other", "board")
        with self.assertRaises(OwnershipError):
            self.target(now=100)
        self.assertEqual(self.store.program_target("other", "board", now=100)["report"]["device_id"], "board")

    def test_field_and_set_order_is_idempotent_but_older_conflict_cannot_replace(self):
        value = report()
        first = self.store.record_capabilities("board", value, now=101)
        reordered = dict(reversed(list(value.items())))
        reordered["modules"] = list(reversed(reordered["modules"]))
        reordered["schema_versions"] = [2, 1]
        self.assertEqual(self.store.record_capabilities("board", reordered, now=101), first)
        for when in (100, 101):
            with self.assertRaises(ConflictError):
                self.store.record_capabilities("board", report(boot_id="older-boot"), now=when)
        self.assertEqual(self.target(now=101)["report"]["boot_id"], "boot-one")
        self.store.record_capabilities("board", report(boot_id="new-boot"), now=102)
        self.assertEqual(self.target(now=102)["report"]["boot_id"], "new-boot")

    def test_unknown_versions_record_without_enabling_source_apis(self):
        changes = [{"runtime_version": "9.0.0"}, {"engine": "other-engine"}, {"sdk": "future-sdk"},
                   {"profile": "future-profile"}, {"schema_versions": [1]}, {"modules": ["canvas", "input"]},
                   {"viewport": {"width": 320, "height": 480}}]
        for index, change in enumerate(changes):
            self.store.record_capabilities("board", report(**change), now=100 + index)
            self.assert_gate("capabilities_incompatible", now=100 + index)
        self.store.record_capabilities("board", report(modules=PROFILE["modules"] + ["future-module"]), now=200)
        self.assert_gate("capabilities_incompatible", now=200)

    def test_second_connection_cannot_replace_newer_server_receipt_with_old_write(self):
        with DeviceRuntimeStore(self.path) as other:
            self.store.record_capabilities("board", report(), now=100)
            other.record_capabilities("board", report(boot_id="newer-boot"), now=101)
            with self.assertRaises(ConflictError):
                self.store.record_capabilities("board", report(boot_id="older-boot"), now=100.5)
            self.assertEqual(self.target(now=101)["report"]["boot_id"], "newer-boot")

    def test_waiting_for_sqlite_writer_cannot_freeze_a_fresh_clock_sample(self):
        self.store.record_capabilities("board", report(), now=100)
        locked, attempted = threading.Event(), threading.Event()
        clock, errors = [129.9], []
        self.store._db.set_trace_callback(lambda sql: attempted.set() if sql == "BEGIN IMMEDIATE" else None)
        def writer():
            try:
                with DeviceRuntimeStore(self.path) as other:
                    with other._transaction():
                        locked.set()
                        if not attempted.wait(2):
                            raise AssertionError("Reader did not attempt its transaction")
                        clock[0] = 130.1
            except BaseException as error:
                errors.append(error)
                locked.set()
        thread = threading.Thread(target=writer)
        thread.start()
        try:
            self.assertTrue(locked.wait(2))
            with patch("backend.device_runtime.time.time", side_effect=lambda: clock[0]):
                self.assert_gate("capabilities_stale")
        finally:
            attempted.set()
            thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])

    def test_invalid_payload_never_refreshes_previous_report(self):
        self.store.record_capabilities("board", report(), now=100)
        invalid = [report(protocol_version=True), report(protocol_version=2), report(extra="PRIVATE_SECRET"),
                   report(boot_id="x" * 129), report(engine="x" * 8193), report(sdk="snowman-☃"),
                   report(profile="bad\nline"), report(schema_versions=[True, 2]),
                   report(schema_versions=[2, 2]), report(schema_versions=[2.0]), report(schema_versions=[]),
                   report(schema_versions=list(range(1, 18))), report(modules=["canvas", "canvas"]),
                   report(modules=[True]), report(modules=["x" * 65]), report(modules=["x" + str(i) for i in range(33)]),
                   report(viewport={"width": True, "height": 432}), report(viewport={"width": 320, "height": 432.0}),
                   report(viewport={"width": 320, "height": 432, "rotation": 0}), report(firmware_elf_sha256="A" * 64),
                   report(firmware_elf_sha256="f" * 65), report(firmware_elf_sha256=False), None, []]
        missing = report()
        del missing["sdk"]
        invalid.append(missing)
        for item in invalid:
            with self.subTest(item=item), self.assertRaises(StoreError):
                self.store.record_capabilities("board", item, now=110)
        self.assertEqual(self.target(now=110)["received_at"], 100)
        self.assert_gate("capabilities_stale", now=131)

    def test_bool_nan_infinite_and_invalid_clock_or_freshness_are_rejected(self):
        for value in (True, False, float("nan"), float("inf"), -1, "100", 10**13, 10**1000):
            with self.subTest(value=value), self.assertRaises(StoreError):
                self.store.record_capabilities("board", report(), now=value)
        self.store.record_capabilities("board", report(), now=100)
        for value in (True, float("nan"), float("inf"), -1, "30", 30.001, 10**1000):
            with self.subTest(value=value), self.assertRaises(StoreError):
                self.target(now=100, max_age=value)

    def test_tampered_stored_payload_or_timestamp_fails_closed(self):
        self.store.record_capabilities("board", report(), now=100)
        payloads = [b"{}", b"{", b"x" * 8193, json.dumps(report()).encode(),
                    json.dumps(report(device_id="other-board")).encode()]
        for raw in payloads:
            self.store._db.execute("UPDATE device_runtime_reports SET payload=?", (raw,))
            with self.assertRaises(IntegrityError):
                self.target(now=100)
        self.store._db.execute("DELETE FROM device_runtime_reports")
        self.store.record_capabilities("board", report(), now=100)
        self.store._db.execute("UPDATE device_runtime_reports SET received_at=-1")
        with self.assertRaises(IntegrityError):
            self.target(now=100)

    def test_report_recording_does_not_supersede_intent_or_change_legacy_delivery(self):
        fixture = Path(__file__).resolve().parents[1] / "contracts/fixtures/tap-sprint.json"
        intent = self.store.accept_intent("owner", "board", "legacy", b"legacy request")
        envelope = self.store.publish("owner", intent["intent_id"], fixture.read_bytes())
        before = self.store.package_for_device("board", envelope["deployment_id"])
        self.assert_gate("capabilities_missing", now=100)
        self.store.record_capabilities("board", report(runtime_version="0.2.0", schema_versions=[1]), now=100)
        self.assert_gate("capabilities_incompatible", now=100)
        self.assertEqual(self.store.desired_for_device("board"), envelope)
        self.assertEqual(self.store.package_for_device("board", envelope["deployment_id"]), before)
        with DeploymentStore(self.path) as legacy:
            self.assertEqual(legacy.desired_for_device("board"), envelope)
            self.assertEqual(legacy.package_for_device("board", envelope["deployment_id"]), before)


if __name__ == "__main__":
    unittest.main()
