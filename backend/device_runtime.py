"""Fresh authenticated-caller capability declarations for schema2 selection.

The caller authenticates the device/session before calling these methods. A
reported ELF hash is an identity claim, not cryptographic runtime attestation.
Legacy delivery methods are inherited unchanged; integration must call the gate
at programmable acceptance, publication and download, not only at generation.
"""

import json
import math
import re
import time

from .deployments import ConflictError, IntegrityError, OwnershipError, StoreError, _token
from .program_store import ProgramStore
from runtime.program import PROFILE

MAX_REPORT_BYTES = 8192
MAX_AGE_SECONDS = 30
FIELDS = {"protocol_version", "device_id", "boot_id", "runtime_version", "schema_versions",
          "engine", "sdk", "profile", "modules", "viewport", "firmware_elf_sha256"}


class CapabilityError(StoreError):
    """Fixed gate outcome; callers can map code without exposing stored input."""

    MESSAGES = {
        "capabilities_missing": "The device has not reported its runtime capabilities.",
        "capabilities_stale": "The device runtime report is no longer fresh.",
        "capabilities_incompatible": "The device runtime does not match this program SDK.",
    }

    def __init__(self, code):
        self.code = code
        super().__init__(self.MESSAGES[code])


def _timestamp(value):
    if type(value) not in (int, float) or not 0 <= value <= 10**12 or not math.isfinite(value):
        raise StoreError("Expected a finite server timestamp")
    return float(value)


def _text(value, maximum=128):
    if (type(value) is not str or not 1 <= len(value) <= maximum
            or any(not 32 <= ord(char) <= 126 for char in value)):
        raise StoreError("Expected bounded printable ASCII text")


def _report(report, device_id):
    if type(report) is not dict or set(report) != FIELDS:
        raise StoreError("Capability fields do not match protocol version 1")
    if type(report["protocol_version"]) is not int or report["protocol_version"] != 1:
        raise StoreError("Unsupported capability protocol version")
    _token(report["device_id"])
    if report["device_id"] != device_id:
        raise OwnershipError("Capability report belongs to another device")
    _token(report["boot_id"])
    for name in ("runtime_version", "engine", "sdk", "profile"):
        _text(report[name])
    schemas = report["schema_versions"]
    if (type(schemas) is not list or not 1 <= len(schemas) <= 16
            or any(type(item) is not int or not 1 <= item <= 65535 for item in schemas)
            or len(set(schemas)) != len(schemas)):
        raise StoreError("Expected distinct bounded schema version integers")
    modules = report["modules"]
    if type(modules) is not list or len(modules) > 32:
        raise StoreError("Expected a bounded module list")
    for item in modules:
        _text(item, 64)
    if len(set(modules)) != len(modules):
        raise StoreError("Expected distinct module names")
    viewport = report["viewport"]
    if (type(viewport) is not dict or set(viewport) != {"width", "height"}
            or any(type(viewport[key]) is not int or not 1 <= viewport[key] <= 16384
                   for key in ("width", "height"))):
        raise StoreError("Expected a bounded integer viewport")
    fingerprint = report["firmware_elf_sha256"]
    if type(fingerprint) is not str or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
        raise StoreError("Expected a lowercase firmware SHA256")
    # Lists represent sets. Canonical ordering keeps idempotency independent of
    # JSON field order or advertised module/schema order.
    canonical = dict(report, schema_versions=sorted(schemas), modules=sorted(modules),
                     viewport=dict(viewport))
    raw = json.dumps(canonical, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")
    if len(raw) > MAX_REPORT_BYTES:
        raise StoreError("Capability report exceeds the byte limit")
    return canonical, raw


class DeviceRuntimeStore(ProgramStore):
    """Separate SQLite instance per thread, as with the parent deployment store."""

    def __init__(self, path):
        super().__init__(path)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS device_runtime_reports (
                device_id TEXT PRIMARY KEY REFERENCES devices(device_id),
                received_at REAL NOT NULL,
                payload BLOB NOT NULL
            )
        """)

    def record_capabilities(self, device_id, report, *, now=None):
        """Record an authenticated device's declaration using server-owned time.

        Timestamp order rejects stale server-side writes. Boot IDs are opaque;
        without a device sequence counter they cannot prove causal boot ordering.
        """
        _token(device_id)
        received_at = _timestamp(time.time() if now is None else now)
        canonical, raw = _report(report, device_id)
        with self._transaction():
            self._device(device_id)
            prior = self._db.execute("SELECT received_at,payload FROM device_runtime_reports WHERE device_id=?",
                                     (device_id,)).fetchone()
            if prior is not None and (received_at < prior["received_at"] or
                    (received_at == prior["received_at"] and raw != prior["payload"])):
                raise ConflictError("A newer or conflicting capability report is already recorded")
            self._db.execute("""
                INSERT INTO device_runtime_reports(device_id,received_at,payload) VALUES (?,?,?)
                ON CONFLICT(device_id) DO UPDATE SET received_at=excluded.received_at,payload=excluded.payload
            """, (device_id, received_at, raw))
        return {"report": canonical, "received_at": received_at}

    def program_target(self, session_id, device_id, *, now=None, max_age=MAX_AGE_SECONDS):
        """Return fresh recognized source compatibility, never physical proof.

        A frozen profile requires exactly its module set, regardless of order.
        Unknown declarations are stored but do not enable extra source APIs.
        """
        with self._transaction():
            return self._program_target(session_id, device_id, now=now, max_age=max_age)

    def _program_target(self, session_id, device_id, *, now=None, max_age=MAX_AGE_SECONDS):
        if now is not None:
            _timestamp(now)
        if (type(max_age) not in (int, float) or not 0 <= max_age <= MAX_AGE_SECONDS
                or not math.isfinite(max_age)):
            raise StoreError("Capability freshness may not exceed 30 seconds")
        self._device(device_id, session_id)
        row = self._db.execute("SELECT received_at,payload FROM device_runtime_reports WHERE device_id=?",
                               (device_id,)).fetchone()
        if row is None:
            raise CapabilityError("capabilities_missing")
        try:
            received_at = _timestamp(row["received_at"])
            raw = row["payload"]
            if type(raw) is not bytes or len(raw) > MAX_REPORT_BYTES:
                raise ValueError()
            report, canonical = _report(json.loads(raw), device_id)
            if canonical != raw:
                raise ValueError()
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise IntegrityError("Stored capability report no longer validates") from None
        # A busy SQLite writer may delay acquiring this transaction. Sample
        # live time after that wait, immediately before the freshness gate.
        current_time = _timestamp(time.time() if now is None else now)
        age = current_time - received_at
        if not 0 <= age <= max_age:
            raise CapabilityError("capabilities_stale")
        if (any(report[key] != PROFILE[key] for key in ("runtime_version", "engine", "sdk", "profile", "viewport"))
                or PROFILE["schema_version"] not in report["schema_versions"]
                or set(PROFILE["modules"]) != set(report["modules"])):
            raise CapabilityError("capabilities_incompatible")
        return {"report": report, "received_at": received_at, "age_seconds": age,
                "supported_modules": list(PROFILE["modules"])}

    def accept_program_intent(self, session_id, device_id, idempotency_key, request):
        """Fresh target selection and request acceptance form one transaction."""
        _token(idempotency_key)
        if type(request) is not bytes or not 1 <= len(request) <= 65536:
            raise StoreError("Request snapshot must contain 1..65536 bytes")
        with self._transaction():
            self._program_target(session_id, device_id)
            return self._accept_intent_locked(session_id, device_id, idempotency_key, request)

    def _check_program_publication(self, intent):
        self._program_target(intent["session_id"], intent["device_id"])

    def _check_package_download(self, device, row):
        if row["schema_version"] == 2:
            self._program_target(device["session_id"], device["device_id"])
