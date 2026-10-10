"""Real request dispatch and SQLite checks; no network/provider claims."""

import io
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.server import Application, Handler, RequestError, single_instance

FIXTURE = (Path(__file__).parent.parent / "contracts/fixtures/tap-sprint.json").read_bytes()


class Socket:
    def __init__(self, request):
        self.input = io.BytesIO(request)
        self.output = bytearray()

    def makefile(self, *args):
        return self.input

    def sendall(self, data):
        self.output.extend(data)

    def settimeout(self, *_):
        pass


def http(app, method, path, role="session", body=b"", content_type="application/json"):
    token = app.config.get(role + "_token", "invalid")
    header = "{} {} HTTP/1.0\r\nHost: demo.test\r\nAuthorization: Bearer {}\r\nContent-Type: {}\r\nContent-Length: {}\r\n\r\n".format(method, path, token, content_type, len(body))
    socket = Socket(header.encode() + body)
    Handler(socket, ("127.0.0.1", 12345), SimpleNamespace(application=app))
    head, payload = bytes(socket.output).split(b"\r\n\r\n", 1)
    return int(head.split(b" ")[1]), head, payload


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = Application(Path(self.temp.name), generator=lambda *_: FIXTURE)

    def tearDown(self):
        self.wait_idle()
        self.temp.cleanup()

    def wait_idle(self):
        deadline = time.monotonic() + 3
        while self.app.busy and time.monotonic() < deadline:
            time.sleep(.005)
        self.assertFalse(self.app.busy)

    def start(self, key="a" * 32, prompt="Create a tap game", uploads=None):
        return self.app.generate({"request_id": key, "prompt": prompt, "uploads": uploads or []})["job_id"]

    def test_real_dispatch_auth_and_role_separation(self):
        for role in ("invalid", "device"):
            self.assertEqual(http(self.app, "GET", "/api/session", role)[0], 401)
        self.assertEqual(http(self.app, "GET", "/api/device/desired", "session")[0], 401)
        self.assertEqual(http(self.app, "GET", "/api/device/desired", "device")[0], 200)
        self.assertEqual(http(self.app, "GET", "/api/session")[0], 200)
        self.assertFalse(self.app.authorized("Bearer nonasciié", "session"))

    def test_second_service_cannot_take_startup_lock(self):
        with single_instance(Path(self.temp.name)):
            with self.assertRaises(BlockingIOError):
                with single_instance(Path(self.temp.name)):
                    self.fail("A second server must not reconcile live jobs")
        with single_instance(Path(self.temp.name)):
            pass

    def test_assets_and_private_path_not_served(self):
        status, header, body = http(self.app, "GET", "/", "invalid")
        self.assertEqual(status, 200)
        self.assertIn(b"Content-Security-Policy:", header)
        self.assertIn(b"Generate and install", body)
        for path in ("/../.env", "/private/service/demo-config.json", "/app.js/../../.env"):
            self.assertEqual(http(self.app, "GET", path)[0], 404)
        self.assertNotIn(self.app.config["device_token"].encode(), body)

    def test_actual_publication_download_and_exact_active_ack(self):
        identifier = self.start()
        self.wait_idle()
        self.assertEqual(self.app.status(identifier)["stage"], "ready")
        code, _, payload = http(self.app, "GET", "/api/device/desired", "device")
        desired = json.loads(payload)["desired"]
        code, _, package = http(self.app, "GET", desired["manifest"]["download_path"], "device")
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(package)["name"], "Tap Sprint")
        manifest = desired["manifest"]
        ack = {"device_id": self.app.config["device_id"], "deployment_id": desired["deployment_id"], "sequence": desired["sequence"],
               "app_id": manifest["app_id"], "version": manifest["version"], "sha256": "0" * 64, "status": "active"}
        self.assertEqual(http(self.app, "POST", "/api/device/ack", "device", json.dumps(ack).encode())[0], 400)
        self.assertEqual(self.app.status(identifier)["stage"], "ready")
        ack["sha256"] = manifest["sha256"]
        self.assertEqual(http(self.app, "POST", "/api/device/ack", "device", json.dumps(ack).encode())[0], 200)
        self.assertEqual(self.app.status(identifier)["stage"], "active")

    def test_same_request_while_busy_is_idempotent_and_changed_request_conflicts(self):
        release = threading.Event()
        self.app.generator = lambda *_: (release.wait(2), FIXTURE)[1]
        identifier = self.start()
        try:
            self.assertEqual(self.start(), identifier)
            with self.assertRaises(RequestError) as conflict:
                self.start(prompt="Different")
            self.assertEqual(conflict.exception.code, "request_conflict")
            with self.assertRaises(RequestError) as busy:
                self.start(key="b" * 32)
            self.assertEqual(busy.exception.code, "generation_busy")
        finally:
            release.set()

    def test_generation_failure_is_not_success_and_releases_worker(self):
        self.app.generator = lambda *_: b"invalid json"
        identifier = self.start()
        self.wait_idle()
        self.assertEqual(self.app.status(identifier)["stage"], "failed")
        self.assertIsNone(self.app.status(identifier)["deployment"])

    def test_failed_job_persists_and_serves_only_allowlisted_diagnostics(self):
        secret = "synthetic_private_provider_text"
        diagnostics = {"phase": "poll", "reason": "interaction_not_completed",
                       "interaction_status": "incomplete", "attempt": 1, "elapsed_ms": 82500,
                       "token_budget": 32768, "artifact_matches": False,
                       "usage": {"total_tokens": 32770, "total_output_tokens": secret,
                                 "total_input_tokens": -1, secret: 123},
                       "step_counts": {"code_execution_call": 1, "model_output": True, secret: 2},
                       "message": secret, "metadata": {"key": secret}, "prompt": secret}
        expected = {"phase": "poll", "reason": "interaction_not_completed",
                    "interaction_status": "incomplete", "attempt": 1, "elapsed_ms": 82500,
                    "token_budget": 32768, "usage": {"total_tokens": 32770},
                    "step_counts": {"code_execution_call": 1}}
        failure = RuntimeError(secret)
        failure.code, failure.diagnostics = "provider_response", diagnostics
        def generate(*_):
            raise failure
        self.app.generator = generate
        identifier = self.start()
        self.wait_idle()
        stored = (self.app.jobs / (identifier + ".json")).read_bytes()
        self.assertEqual(json.loads(stored)["diagnostics"], expected)
        code, _, payload = http(self.app, "GET", "/api/jobs/" + identifier)
        record = json.loads(payload)
        self.assertEqual(code, 200)
        self.assertEqual(record["stage"], "failed")
        self.assertEqual(record["detail"], "provider_response")
        self.assertEqual(record["diagnostics"], expected)
        self.assertIsNone(record["deployment"])
        self.assertNotIn(secret.encode(), stored + payload)
        self.assertEqual(http(self.app, "GET", "/api/jobs/" + identifier, "device")[0], 401)
        # Disk content is filtered again at the response boundary, even if changed later.
        changed = json.loads(stored)
        changed["diagnostics"] = dict(diagnostics, reason=secret, elapsed_ms=10**13)
        (self.app.jobs / (identifier + ".json")).write_text(json.dumps(changed))
        code, _, payload = http(self.app, "GET", "/api/jobs/" + identifier)
        self.assertEqual(code, 200)
        filtered = json.loads(payload)["diagnostics"]
        self.assertNotIn("reason", filtered)
        self.assertNotIn("elapsed_ms", filtered)
        self.assertNotIn(secret.encode(), payload)

    def test_unknown_exception_code_and_nonobject_diagnostics_never_echo(self):
        secret = "private_secret_as_lowercase_code"
        failure = RuntimeError(secret)
        failure.code, failure.diagnostics = secret, [secret]
        def generate(*_):
            raise failure
        self.app.generator = generate
        identifier = self.start()
        self.wait_idle()
        code, _, payload = http(self.app, "GET", "/api/jobs/" + identifier)
        record = json.loads(payload)
        self.assertEqual(code, 200)
        self.assertEqual(record["detail"], "generation_failed")
        self.assertEqual(record["diagnostics"], {})
        self.assertNotIn(secret.encode(), payload)
        self.assertNotIn(secret, (self.app.jobs / (identifier + ".json")).read_text())
        with self.app.store() as store:
            self.assertEqual(store.get_intent(self.app.config["session_id"], identifier)["error_code"], "generation_failed")

    def test_upload_freezes_bytes_and_rejects_changed_file(self):
        code, _, body = http(self.app, "POST", "/api/uploads", body=b"image input fixture", content_type="image/png")
        self.assertEqual(code, 201)
        identifier = json.loads(body)["upload_id"]
        (self.app.uploads / identifier).write_bytes(b"changed")
        with self.assertRaises(RequestError) as failure:
            self.start(uploads=[identifier])
        self.assertEqual(failure.exception.code, "upload_integrity_failed")
        self.assertEqual(http(self.app, "POST", "/api/uploads", body=b"x", content_type="text/html")[0], 400)

    def test_restart_retains_publication_and_idempotency(self):
        identifier = self.start()
        self.wait_idle()
        self.app.progress(identifier, "validating", "Interrupted after publication.")
        self.app = Application(Path(self.temp.name), generator=lambda *_: FIXTURE)
        self.assertEqual(self.start(), identifier)
        self.assertEqual(self.app.status(identifier)["stage"], "ready")
        self.assertIsNotNone(self.app.status(identifier)["deployment"])

    def test_restart_marks_accepted_job_failed(self):
        with patch("backend.server.threading.Thread.start"):
            identifier = self.start()
        self.app.busy = False
        self.app = Application(Path(self.temp.name), generator=lambda *_: FIXTURE)
        self.assertEqual(self.app.status(identifier)["stage"], "failed")

    def test_job_record_write_failure_does_not_wedge_worker(self):
        with patch("backend.server.save_private", side_effect=OSError("synthetic storage failure")):
            with self.assertRaises(RequestError):
                self.start()
        self.assertFalse(self.app.busy)
        failed = self.start()
        self.assertEqual(self.app.status(failed)["stage"], "failed")
        identifier = self.start(key="b" * 32)
        self.wait_idle()
        self.assertEqual(self.app.status(identifier)["stage"], "ready")

    def test_thread_start_failure_is_terminal_and_retryable_as_new_intent(self):
        with patch("backend.server.threading.Thread.start", side_effect=RuntimeError("synthetic failure")):
            with self.assertRaises(RequestError):
                self.start()
        self.assertFalse(self.app.busy)
        identifier = self.start(key="b" * 32)
        self.wait_idle()
        self.assertEqual(self.app.status(identifier)["stage"], "ready")


if __name__ == "__main__":
    unittest.main()
