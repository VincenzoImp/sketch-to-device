"""Ordered authenticated recovery reports with permanent activation quarantine.

The caller authenticates device_id. Reports preserve historical ACKs and never
publish packages. A recorded event can acknowledge the device's durable outbox
without rewriting a newer, unrelated active deployment.
"""

import json
import re

from .deployments import ConflictError, IntegrityError, OwnershipError, StoreError, _token
from .device_runtime import DeviceRuntimeStore

FIELDS = {"protocol_version", "report_id", "recovery_seq", "failed", "recovered", "error_code"}
IDENTITY_FIELDS = {"deployment_id", "sequence", "app_id", "version", "sha256"}
ERROR_CODES = {"runtime_error", "activation_failed", "recovery_failed"}
MAX_SEQUENCE = 2**63 - 1


def _identity(value):
    if type(value) is not dict or set(value) != IDENTITY_FIELDS:
        raise StoreError("Recovery identity fields do not match the contract")
    for name in ("deployment_id", "app_id"):
        _token(value[name])
    for name, maximum in (("sequence", MAX_SEQUENCE), ("version", 2**31 - 1)):
        if type(value[name]) is not int or not 1 <= value[name] <= maximum:
            raise StoreError("Recovery identity requires positive bounded integers")
    if type(value["sha256"]) is not str or not re.fullmatch(r"[0-9a-f]{64}", value["sha256"]):
        raise StoreError("Recovery identity requires a lowercase SHA256")


def _report(body):
    if type(body) is not dict or set(body) != FIELDS:
        raise StoreError("Recovery report fields do not match the contract")
    if type(body["protocol_version"]) is not int or body["protocol_version"] != 1:
        raise StoreError("Unsupported recovery protocol version")
    _token(body["report_id"])
    if type(body["recovery_seq"]) is not int or not 1 <= body["recovery_seq"] <= MAX_SEQUENCE:
        raise StoreError("Expected a positive bounded recovery sequence")
    if type(body["error_code"]) is not str or body["error_code"] not in ERROR_CODES:
        raise StoreError("Unsupported recovery error code")
    _identity(body["failed"])
    if body["recovered"] is not None:
        _identity(body["recovered"])
        if body["recovered"]["sequence"] >= body["failed"]["sequence"]:
            raise IntegrityError("A recovered deployment must precede the failed deployment")
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")
    if len(raw) > 4096:
        raise StoreError("Recovery report exceeds the byte limit")
    return raw


class RecoveryStore(DeviceRuntimeStore):
    def __init__(self, path):
        super().__init__(path)
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS recovery_reports (
                device_id TEXT NOT NULL REFERENCES devices(device_id),
                report_id TEXT NOT NULL,
                recovery_seq INTEGER NOT NULL,
                payload BLOB NOT NULL,
                applied INTEGER NOT NULL,
                PRIMARY KEY(device_id, report_id),
                UNIQUE(device_id, recovery_seq)
            );
        """)

    def _recovery_identity(self, device_id, identity):
        row = self._checked_deployment(identity["deployment_id"])
        if row["device_id"] != device_id:
            raise OwnershipError("Recovery identity belongs to another device")
        if any(row[name] != identity[name] for name in IDENTITY_FIELDS):
            raise IntegrityError("Recovery identity does not match its stored deployment")
        return row

    def recovery_for_intent(self, session_id, intent_id):
        """Expose the exact historical recovery affecting this owned request."""
        with self._transaction():
            self._intent(session_id, intent_id)
            row = self._db.execute("""
                SELECT r.payload FROM recovery_reports r
                JOIN deployment_quarantine q ON q.device_id=r.device_id AND q.recovery_seq=r.recovery_seq
                JOIN deployments d ON d.deployment_id=q.deployment_id
                WHERE d.intent_id=? AND d.session_id=?
            """, (intent_id, session_id)).fetchone()
            if row is None:
                return None
            value = json.loads(row["payload"])
            return {"error_code": value["error_code"], "recovered": value["recovered"]}

    def record_recovery(self, device_id, body):
        """Atomically record a contiguous event, quarantine and reconcile state.

        The durable per-device sequence starts at1 and survives boots. Gaps must
        be retried after preceding outbox entries. Duplicate responses preserve
        the original applied flag: it describes that event, not current health.
        A null recovered identity means the built-in app, never an unknown app.
        A known older active identity may reflect a lost activation ACK, so it is
        reconciled too. Only a strictly newer active deployment is preserved.
        """
        _token(device_id)
        raw = _report(body)
        report_id, sequence = body["report_id"], body["recovery_seq"]
        with self._transaction():
            device = self._device(device_id)
            prior = self._db.execute("SELECT payload,applied FROM recovery_reports WHERE device_id=? AND report_id=?",
                                     (device_id, report_id)).fetchone()
            if prior is not None:
                if raw != prior["payload"]:
                    raise ConflictError("Recovery report identity changed its payload")
                return {"report_id": report_id, "recovery_seq": sequence,
                        "recorded": False, "applied": bool(prior["applied"])}
            last = self._db.execute("SELECT COALESCE(MAX(recovery_seq),0) FROM recovery_reports WHERE device_id=?",
                                    (device_id,)).fetchone()[0]
            if sequence != last + 1:
                raise ConflictError("Recovery reports must arrive in contiguous sequence order")
            failed = self._recovery_identity(device_id, body["failed"])
            recovered = (self._recovery_identity(device_id, body["recovered"])
                         if body["recovered"] is not None else None)
            recovered_id = recovered["deployment_id"] if recovered is not None else None
            if recovered_id is not None and self._db.execute(
                    "SELECT 1 FROM deployment_quarantine WHERE deployment_id=?", (recovered_id,)).fetchone():
                raise IntegrityError("A quarantined deployment cannot be restored")
            current = (self._checked_deployment(device["active_id"])
                       if device["active_id"] is not None else None)
            if current is not None and current["device_id"] != device_id:
                raise IntegrityError("Current active deployment belongs to another device")
            applied = current is None or current["sequence"] <= failed["sequence"]
            self._db.execute("INSERT OR IGNORE INTO deployment_quarantine VALUES (?,?,?)",
                             (failed["deployment_id"], device_id, sequence))
            self._db.execute("UPDATE deployments SET status='failed' WHERE deployment_id=?",
                             (failed["deployment_id"],))
            if applied:
                self._db.execute("UPDATE devices SET active_id=? WHERE device_id=?", (recovered_id, device_id))
                if recovered_id is not None:
                    self._db.execute("UPDATE deployments SET status='active' WHERE deployment_id=?", (recovered_id,))
            if device["desired_id"] == failed["deployment_id"]:
                self._db.execute("UPDATE devices SET desired_id=NULL WHERE device_id=?", (device_id,))
            self._db.execute("INSERT INTO recovery_reports VALUES (?,?,?,?,?)",
                             (device_id, report_id, sequence, raw, int(applied)))
            return {"report_id": report_id, "recovery_seq": sequence, "recorded": True, "applied": bool(applied)}
