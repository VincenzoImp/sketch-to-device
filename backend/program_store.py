"""Durable immutable program candidates and trusted execution receipts.

Only server orchestration calls record_run after its own process execution.
Neither this method nor arbitrary receipt content is an agent-facing endpoint.
"""

import hashlib
import json
import uuid

from backend.deployments import (ConflictError, DeploymentStore, IntegrityError,
                                 OwnershipError, StoreError, _token)
from runtime.program import LIMITS, assemble_program, program_report


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class ProgramStore(DeploymentStore):
    def __init__(self, path):
        super().__init__(path)
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS program_candidates (
                candidate_id TEXT PRIMARY KEY,
                intent_id TEXT NOT NULL REFERENCES intents(intent_id),
                session_id TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                body BLOB NOT NULL,
                UNIQUE(intent_id, sha256)
            );
            CREATE TABLE IF NOT EXISTS program_runs (
                receipt_id TEXT PRIMARY KEY,
                candidate_id TEXT NOT NULL REFERENCES program_candidates(candidate_id),
                candidate_sha256 TEXT NOT NULL,
                runner_sha256 TEXT NOT NULL,
                scenario BLOB NOT NULL,
                scenario_sha256 TEXT NOT NULL,
                result BLOB NOT NULL,
                succeeded INTEGER NOT NULL
            );
        """)

    def _current_intent(self, session_id, intent_id, *, published=False):
        intent = self._intent(session_id, intent_id)
        device = self._device(intent["device_id"], session_id)
        states = {"accepted", "published"} if published else {"accepted"}
        if device["current_intent_id"] != intent_id or intent["status"] not in states:
            raise ConflictError("Program job is no longer the current install intent")
        return intent

    def _candidate(self, session_id, intent_id, candidate_id):
        self._intent(session_id, intent_id)
        _token(candidate_id)
        row = self._db.execute("SELECT * FROM program_candidates WHERE candidate_id=?", (candidate_id,)).fetchone()
        if row is None or row["session_id"] != session_id or row["intent_id"] != intent_id:
            raise OwnershipError("Candidate is not owned by this job")
        report = program_report(row["body"])
        if row["sha256"] != report["sha256"]:
            raise IntegrityError("Candidate bytes changed after assembly")
        reservation = self._db.execute("SELECT version FROM program_versions WHERE session_id=? AND app_id=? AND intent_id=?",
                                       (session_id, report["app_id"], intent_id)).fetchone()
        if reservation is None or reservation["version"] != report["version"]:
            raise IntegrityError("Candidate no longer matches its reserved version")
        return row, report

    def prepare_candidate(self, session_id, intent_id, *, app_id, name, source, assets, requires):
        """Reserve publication version, assemble and freeze before any execution."""
        _token(app_id)
        with self._transaction():
            self._current_intent(session_id, intent_id)
            row = self._db.execute("SELECT version FROM program_versions WHERE session_id=? AND app_id=? AND intent_id=?",
                                   (session_id, app_id, intent_id)).fetchone()
            version = row["version"] if row else self._next_version(session_id, app_id)
            body = assemble_program(app_id=app_id, name=name, source=source, version=version,
                                    assets=assets, requires=requires)
            if row is None:
                self._db.execute("INSERT INTO program_versions VALUES (?,?,?,?)",
                                 (session_id, app_id, intent_id, version))
            sha = digest(body)
            prior = self._db.execute("SELECT candidate_id FROM program_candidates WHERE intent_id=? AND sha256=?",
                                     (intent_id, sha)).fetchone()
            candidate_id = prior["candidate_id"] if prior else "candidate_" + uuid.uuid4().hex
            if prior is None:
                self._db.execute("INSERT INTO program_candidates VALUES (?,?,?,?,?)",
                                 (candidate_id, intent_id, session_id, sha, body))
            # Reading through the verifier also checks an existing idempotent row.
            _, report = self._candidate(session_id, intent_id, candidate_id)
            return dict(report, candidate_id=candidate_id)

    def candidate_bytes(self, session_id, intent_id, candidate_id):
        with self._transaction():
            self._current_intent(session_id, intent_id)
            return self._candidate(session_id, intent_id, candidate_id)[0]["body"]

    def record_run(self, session_id, intent_id, candidate_id, *, runner_sha256,
                   scenario, result, succeeded):
        """Trusted server-only boundary, after executing the exact candidate.

        The integration must verify the process status and bounded output itself;
        a model cannot call this method or supply succeeded through a tool schema.
        """
        if (type(runner_sha256) is not str or len(runner_sha256) != 64
                or any(c not in "0123456789abcdef" for c in runner_sha256)
                or type(scenario) is not bytes or not 1 <= len(scenario) <= LIMITS["scenario_bytes"]
                or type(result) is not dict or type(succeeded) is not bool):
            raise StoreError("Invalid trusted runner record")
        try:
            result_bytes = json.dumps(result, allow_nan=False, sort_keys=True,
                                      separators=(",", ":")).encode()
        except (ValueError, TypeError, RecursionError):
            raise StoreError("Runner result is not bounded JSON") from None
        if len(result_bytes) > 65536:
            raise StoreError("Runner result is too large")
        with self._transaction():
            self._current_intent(session_id, intent_id)
            row, report = self._candidate(session_id, intent_id, candidate_id)
            receipt_id = "receipt_" + uuid.uuid4().hex
            self._db.execute("INSERT INTO program_runs VALUES (?,?,?,?,?,?,?,?)",
                             (receipt_id, candidate_id, report["sha256"], runner_sha256,
                              scenario, digest(scenario), result_bytes, int(succeeded)))
            return {"receipt_id": receipt_id, "candidate_id": candidate_id,
                    "sha256": row["sha256"], "execution_succeeded": succeeded}

    def publish_program(self, session_id, intent_id, receipt_id, *, expected_runner_sha256):
        """Resolve a server receipt and publish unchanged bytes exactly once."""
        _token(receipt_id)
        with self._transaction():
            intent = self._current_intent(session_id, intent_id, published=True)
            receipt = self._db.execute("SELECT * FROM program_runs WHERE receipt_id=?", (receipt_id,)).fetchone()
            if receipt is None:
                raise OwnershipError("Unknown execution receipt")
            row, report = self._candidate(session_id, intent_id, receipt["candidate_id"])
            if (not receipt["succeeded"] or receipt["candidate_sha256"] != report["sha256"]
                    or receipt["runner_sha256"] != expected_runner_sha256
                    or digest(receipt["scenario"]) != receipt["scenario_sha256"]):
                raise IntegrityError("Receipt does not certify this exact candidate")
            prior = self._db.execute("SELECT * FROM deployments WHERE intent_id=?", (intent_id,)).fetchone()
            if prior:
                if prior["sha256"] != report["sha256"] or prior["body"] != row["body"]:
                    raise ConflictError("A different candidate already completed this job")
                return self._envelope(self._checked_deployment(prior["deployment_id"]))
            deployment_id = "deployment_" + uuid.uuid4().hex
            self._db.execute("INSERT INTO deployments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                             (deployment_id, intent_id, session_id, intent["device_id"], intent["sequence"],
                              report["app_id"], report["version"], 2, report["sha256"], report["size_bytes"],
                              report["min_runtime_version"], report["sha256"], row["body"], "queued"))
            self._db.execute("UPDATE intents SET status='published' WHERE intent_id=?", (intent_id,))
            self._db.execute("UPDATE devices SET desired_id=? WHERE device_id=?", (deployment_id, intent["device_id"]))
            return self._envelope(self._checked_deployment(deployment_id))
