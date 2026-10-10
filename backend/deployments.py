"""Transactional install intent, exact-byte publication, and ACK accounting.

Callers must authenticate session/device identities before using this store.
Ownership checks here prevent cross-session/device access; they are not login
or token verification. bind_device is trusted local setup, never a public API.
"""

import hashlib
import json
import re
import sqlite3
import uuid
from contextlib import contextmanager

from runtime.validation import CAPABILITIES, ValidationError, decode_json, package_report


class StoreError(ValueError):
    """Invalid local store operation."""


class OwnershipError(StoreError):
    """The authenticated caller does not own this resource."""


class ConflictError(StoreError):
    """An idempotency key or install intent conflicts with recorded state."""


class IntegrityError(StoreError):
    """Stored package bytes and recorded identity disagree."""


_TOKEN = re.compile(r"[A-Za-z0-9_.-]{1,128}", re.ASCII)
_PROGRESS = {"queued": 0, "downloading": 1, "validating": 2, "activating": 3,
             "active": 4}
_ACK_FIELDS = {"device_id", "deployment_id", "sequence", "app_id", "version",
               "sha256", "status"}
_DEVICE_IDENTITY_ONLY = object()


def _token(value):
    if type(value) is not str or not _TOKEN.fullmatch(value):
        raise StoreError("Expected a nonempty bounded ASCII identifier")


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


class DeploymentStore:
    """Use a separate instance/connection in each worker thread or process."""

    def __init__(self, path):
        self._db = sqlite3.connect(str(path), timeout=5, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.execute("PRAGMA synchronous = FULL")
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY
            );
            CREATE TABLE IF NOT EXISTS devices (
                device_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES sessions(session_id),
                sequence INTEGER NOT NULL DEFAULT 0,
                current_intent_id TEXT,
                desired_id TEXT,
                active_id TEXT
            );
            CREATE TABLE IF NOT EXISTS intents (
                intent_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES sessions(session_id),
                device_id TEXT NOT NULL REFERENCES devices(device_id),
                idempotency_key TEXT NOT NULL,
                request BLOB NOT NULL,
                sequence INTEGER NOT NULL,
                status TEXT NOT NULL,
                error_code TEXT,
                UNIQUE(session_id, idempotency_key),
                UNIQUE(device_id, sequence)
            );
            CREATE TABLE IF NOT EXISTS deployments (
                deployment_id TEXT PRIMARY KEY,
                intent_id TEXT NOT NULL UNIQUE REFERENCES intents(intent_id),
                session_id TEXT NOT NULL,
                device_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                app_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                schema_version INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                min_runtime_version TEXT NOT NULL,
                source_sha256 TEXT NOT NULL,
                body BLOB NOT NULL,
                status TEXT NOT NULL,
                UNIQUE(session_id, app_id, version)
            );
            CREATE TABLE IF NOT EXISTS acknowledgments (
                ack_id INTEGER PRIMARY KEY,
                deployment_id TEXT NOT NULL REFERENCES deployments(deployment_id),
                status TEXT NOT NULL,
                error_code TEXT NOT NULL,
                UNIQUE(deployment_id, status, error_code)
            );
        """)

    def close(self):
        self._db.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    @contextmanager
    def _transaction(self):
        self._db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self._db.commit()
        except BaseException:
            self._db.rollback()
            raise

    def _device(self, device_id, session_id=_DEVICE_IDENTITY_ONLY):
        _token(device_id)
        if session_id is not _DEVICE_IDENTITY_ONLY:
            _token(session_id)
        row = self._db.execute("SELECT * FROM devices WHERE device_id=?", (device_id,)).fetchone()
        if row is None or (session_id is not _DEVICE_IDENTITY_ONLY and row["session_id"] != session_id):
            raise OwnershipError("Device is not bound to this caller")
        return row

    def _intent(self, session_id, intent_id):
        _token(session_id)
        _token(intent_id)
        row = self._db.execute("SELECT * FROM intents WHERE intent_id=?", (intent_id,)).fetchone()
        if row is None or row["session_id"] != session_id:
            raise OwnershipError("Intent is not owned by this session")
        return row

    @staticmethod
    def _intent_result(row):
        return {key: row[key] for key in
                ("intent_id", "session_id", "device_id", "sequence", "status", "error_code")}

    @staticmethod
    def _envelope(row):
        manifest = {key: row[key] for key in
                    ("app_id", "version", "schema_version", "sha256", "size_bytes",
                     "min_runtime_version")}
        manifest["download_path"] = "/api/apps/{}/versions/{}".format(row["app_id"], row["version"])
        return {"deployment_id": row["deployment_id"], "sequence": row["sequence"],
                "manifest": manifest}

    def _checked_deployment(self, deployment_id):
        row = self._db.execute("SELECT * FROM deployments WHERE deployment_id=?",
                               (deployment_id,)).fetchone()
        if row is None:
            raise IntegrityError("Recorded deployment is missing")
        intent = self._db.execute("SELECT * FROM intents WHERE intent_id=?", (row["intent_id"],)).fetchone()
        if intent is None or any(intent[key] != row[key] for key in ("session_id", "device_id", "sequence")):
            raise IntegrityError("Stored deployment and install intent disagree")
        try:
            report = package_report(row["body"])
        except ValidationError as exc:
            raise IntegrityError("Stored package no longer validates") from exc
        if any(report[key] != row[key] for key in
               ("app_id", "version", "schema_version", "sha256", "size_bytes")):
            raise IntegrityError("Stored package identity or integrity mismatch")
        return row

    def bind_device(self, session_id, device_id):
        """Trusted setup/rebinding; retain known active package, revoke old intent."""
        _token(session_id)
        _token(device_id)
        with self._transaction():
            self._db.execute("INSERT OR IGNORE INTO sessions VALUES (?)", (session_id,))
            previous = self._db.execute("SELECT * FROM devices WHERE device_id=?", (device_id,)).fetchone()
            if previous is None:
                self._db.execute("INSERT INTO devices(device_id,session_id) VALUES (?,?)",
                                 (device_id, session_id))
            elif previous["session_id"] != session_id:
                self._supersede(previous)
                self._db.execute("UPDATE devices SET session_id=?,current_intent_id=NULL,desired_id=NULL WHERE device_id=?",
                                 (session_id, device_id))

    def _supersede(self, device):
        self._db.execute("UPDATE intents SET status='superseded' WHERE intent_id=? AND status IN ('accepted','published')",
                         (device["current_intent_id"],))
        self._db.execute("UPDATE deployments SET status='superseded' WHERE deployment_id=? AND status!='active'",
                         (device["desired_id"],))

    def accept_intent(self, session_id, device_id, idempotency_key, request, *, require_idle=False):
        """Freeze exact request bytes; whitespace changes count as changed input."""
        _token(idempotency_key)
        if type(request) is not bytes or not 1 <= len(request) <= 65536:
            raise StoreError("Request snapshot must contain 1..65536 bytes")
        with self._transaction():
            device = self._device(device_id, session_id)
            prior = self._db.execute("SELECT * FROM intents WHERE session_id=? AND idempotency_key=?",
                                     (session_id, idempotency_key)).fetchone()
            if prior is not None:
                if prior["device_id"] != device_id or prior["request"] != request:
                    raise ConflictError("Idempotency key was used for a different request")
                return self._intent_result(prior)
            if require_idle and device["current_intent_id"]:
                current = self._intent(session_id, device["current_intent_id"])
                if current["status"] == "accepted":
                    raise ConflictError("Generation is in progress")
            self._supersede(device)
            intent_id = "intent_" + uuid.uuid4().hex
            sequence = device["sequence"] + 1
            self._db.execute("INSERT INTO intents VALUES (?,?,?,?,?,?,?,NULL)",
                             (intent_id, session_id, device_id, idempotency_key, request, sequence, "accepted"))
            self._db.execute("UPDATE devices SET sequence=?,current_intent_id=?,desired_id=NULL WHERE device_id=?",
                             (sequence, intent_id, device_id))
            return self._intent_result(self._intent(session_id, intent_id))

    def get_intent(self, session_id, intent_id):
        return self._intent_result(self._intent(session_id, intent_id))

    def fail_intent(self, session_id, intent_id, error_code):
        """Record a generation failure without changing any installed package."""
        _token(error_code)
        with self._transaction():
            intent = self._intent(session_id, intent_id)
            self._device(intent["device_id"], session_id)
            if intent["status"] == "failed" and intent["error_code"] == error_code:
                return
            if intent["status"] != "accepted":
                raise ConflictError("Only an accepted intent can fail generation")
            self._db.execute("UPDATE intents SET status='failed',error_code=? WHERE intent_id=?",
                             (error_code, intent_id))

    def publish(self, session_id, intent_id, artifact):
        """Assign version, validate exact final bytes, and publish only current intent."""
        app = decode_json(artifact)
        if type(app) is not dict or type(app.get("app_id")) is not str:
            raise StoreError("Artifact must be an AppSpec object")
        source_hash = _digest(artifact)
        with self._transaction():
            intent = self._intent(session_id, intent_id)
            device = self._device(intent["device_id"], session_id)
            if device["current_intent_id"] != intent_id or intent["status"] not in ("accepted", "published"):
                raise ConflictError("Only the current accepted install intent can publish")
            previous = self._db.execute("SELECT * FROM deployments WHERE intent_id=?", (intent_id,)).fetchone()
            if previous is not None:
                if previous["source_sha256"] != source_hash:
                    raise ConflictError("Intent was already published from a different artifact")
                return self._envelope(self._checked_deployment(previous["deployment_id"]))
            version = self._db.execute("SELECT COALESCE(MAX(version),0)+1 FROM deployments WHERE session_id=? AND app_id=?",
                                       (session_id, app["app_id"])).fetchone()[0]
            app["version"] = version
            body = json.dumps(app, ensure_ascii=True, allow_nan=False, sort_keys=True,
                              separators=(",", ":")).encode("utf-8")
            report = package_report(body)
            deployment_id = "deployment_" + uuid.uuid4().hex
            self._db.execute("INSERT INTO deployments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                             (deployment_id, intent_id, session_id, intent["device_id"], intent["sequence"],
                              report["app_id"], version, report["schema_version"], report["sha256"],
                              report["size_bytes"], CAPABILITIES["runtime_version"], source_hash, body, "queued"))
            self._db.execute("UPDATE intents SET status='published' WHERE intent_id=?", (intent_id,))
            self._db.execute("UPDATE devices SET desired_id=? WHERE device_id=?",
                             (deployment_id, intent["device_id"]))
            return self._envelope(self._checked_deployment(deployment_id))

    def desired_for_device(self, authenticated_device_id):
        with self._transaction():
            device = self._device(authenticated_device_id)
            return (self._envelope(self._checked_deployment(device["desired_id"]))
                    if device["desired_id"] else None)

    def package_for_device(self, authenticated_device_id, deployment_id):
        with self._transaction():
            device = self._device(authenticated_device_id)
            if device["desired_id"] != deployment_id:
                raise OwnershipError("Device may download only its desired deployment")
            row = self._checked_deployment(deployment_id)
            if row["device_id"] != authenticated_device_id:
                raise OwnershipError("Deployment belongs to another device")
            return row["body"]

    def active_for_session(self, session_id, device_id):
        """Return last accepted active identity, not proof of current physical health."""
        with self._transaction():
            device = self._device(device_id, session_id)
            return (self._envelope(self._checked_deployment(device["active_id"]))
                    if device["active_id"] else None)

    def record_ack(self, authenticated_device_id, ack):
        if (type(ack) is not dict or not _ACK_FIELDS <= set(ack)
                or set(ack) - _ACK_FIELDS - {"error_code"}
                or type(ack["sequence"]) is not int or type(ack["version"]) is not int
                or type(ack["status"]) is not str
                or ack["status"] not in {"downloading", "validating", "activating", "active", "failed"}):
            raise StoreError("Malformed acknowledgment")
        for key in ("device_id", "deployment_id", "app_id", "sha256", "status"):
            _token(ack[key])
        error_code = ack.get("error_code", "")
        if error_code:
            _token(error_code)
            if ack["status"] != "failed":
                raise StoreError("Only failure acknowledgments carry an error code")
        elif "error_code" in ack:
            raise StoreError("Error code must be a nonempty identifier when supplied")
        with self._transaction():
            device = self._device(authenticated_device_id)
            row = self._checked_deployment(ack["deployment_id"])
            if ack["device_id"] != authenticated_device_id or row["device_id"] != authenticated_device_id:
                raise OwnershipError("Acknowledgment belongs to another device")
            if any(ack[key] != row[key] for key in ("sequence", "app_id", "version", "sha256")):
                raise IntegrityError("Acknowledgment identity does not match its deployment")
            recorded = self._db.execute("INSERT OR IGNORE INTO acknowledgments(deployment_id,status,error_code) VALUES (?,?,?)",
                                        (row["deployment_id"], ack["status"], error_code)).rowcount
            current = (device["desired_id"] == row["deployment_id"]
                       and device["current_intent_id"] == row["intent_id"]
                       and device["session_id"] == row["session_id"])
            if current and row["status"] not in ("active", "failed"):
                if ack["status"] == "failed":
                    self._db.execute("UPDATE deployments SET status='failed' WHERE deployment_id=?", (row["deployment_id"],))
                    self._db.execute("UPDATE devices SET desired_id=NULL WHERE device_id=?", (authenticated_device_id,))
                elif _PROGRESS[ack["status"]] > _PROGRESS.get(row["status"], -1):
                    self._db.execute("UPDATE deployments SET status=? WHERE deployment_id=?", (ack["status"], row["deployment_id"]))
                    if ack["status"] == "active":
                        self._db.execute("UPDATE devices SET active_id=? WHERE device_id=?", (row["deployment_id"], authenticated_device_id))
            final = self._db.execute("SELECT status FROM deployments WHERE deployment_id=?", (row["deployment_id"],)).fetchone()[0]
            return {"recorded": bool(recorded), "current_success": bool(current and final == "active"),
                    "deployment_id": row["deployment_id"]}

    def ack_history(self, session_id, intent_id):
        """Historical receipt records never stand in for current deployment success."""
        self._intent(session_id, intent_id)
        return [dict(row) for row in self._db.execute(
            "SELECT a.status,a.error_code FROM acknowledgments a JOIN deployments d USING(deployment_id) WHERE d.intent_id=? ORDER BY a.ack_id",
            (intent_id,))]
