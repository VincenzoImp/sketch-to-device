"""Single-user companion service with authenticated device delivery.

Run behind HTTPS for the phone. The service can also serve file-upload based
input over a trusted LAN during bring-up. Provider work runs in one worker.
"""

import argparse
import fcntl
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
import uuid
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from backend.deployments import ConflictError, DeploymentStore, StoreError
from backend.device_runtime import CapabilityError
from backend.device_recovery import RecoveryStore
from backend.media_limits import MAX_ATTACHMENTS, MAX_TOTAL_MEDIA_BYTES, MAX_UPLOAD_BYTES
from backend.providers import ERROR_MESSAGES, safe_diagnostics

ROOT = Path(__file__).absolute().parent.parent
MAX_UPLOAD = MAX_UPLOAD_BYTES
MAX_TOTAL_MEDIA = MAX_TOTAL_MEDIA_BYTES
MEDIA_TYPES = {"image/jpeg", "image/png", "image/webp", "audio/wav",
               "audio/x-wav", "audio/webm", "audio/mp4", "audio/mpeg",
               "audio/ogg", "video/mp4", "video/webm", "video/quicktime"}
ID = re.compile(r"[a-f0-9]{32}\Z")
ASSETS = {"/": ("index.html", "text/html; charset=utf-8"),
          "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/style.css": ("style.css", "text/css; charset=utf-8")}


class RequestError(Exception):
    def __init__(self, code, status=400):
        self.code, self.status = code, status


def save_private(path, value):
    """Replace a private JSON record atomically, without printing its contents."""
    raw = json.dumps(value, separators=(",", ":")).encode()
    temporary = path.with_name(path.name + ".tmp-" + secrets.token_hex(4))
    descriptor = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(str(temporary), str(path))


def configure(directory):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / "demo-config.json"
    if not path.exists():
        save_private(path, {"session_id": "demo", "device_id": "waveshare-p4",
                            "session_token": secrets.token_urlsafe(32),
                            "device_token": secrets.token_urlsafe(32)})
    config = json.loads(path.read_text())
    if any(type(config.get(key)) is not str or len(config[key]) < 32
           for key in ("session_token", "device_token")):
        raise ValueError("Invalid private service configuration")
    return config


@contextmanager
def single_instance(directory):
    """Lock before startup reconciliation so another process cannot fail live jobs."""
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(str(directory / "server.lock"), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(descriptor)


@contextmanager
def generation_gate(directory, exclusive=False):
    """Coordinate acceptance with a local supervisor restart across processes."""
    descriptor = os.open(str(Path(directory) / "restart.lock"), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(descriptor, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RequestError("service_restarting", 503) from None
        yield
    finally:
        os.close(descriptor)


class Application:
    def __init__(self, directory, generator=None, program_generator=None):
        self.directory = Path(directory)
        self.config = configure(self.directory)
        self.database = self.directory / "deployments.sqlite"
        self.uploads = self.directory / "uploads"
        self.jobs = self.directory / "jobs"
        for folder in (self.uploads, self.jobs):
            folder.mkdir(exist_ok=True, mode=0o700)
        self.generator = generator
        self.program_generator = program_generator
        # An explicitly supplied legacy generator remains available for legacy
        # integration tests. Normal product requests target the programmable SDK.
        self.programmable = generator is None
        self.lock = threading.Lock()
        self.busy = False
        self.requests = {}
        self.device_seen = None
        with self.store() as store:
            # Rebinding would revoke desired work. Provision only a new database.
            try:
                store.active_for_session(self.config["session_id"], self.config["device_id"])
            except StoreError:
                store.bind_device(self.config["session_id"], self.config["device_id"])
            for path in self.jobs.glob("*.json"):
                record = json.loads(path.read_text())
                self.requests[record["request_id"]] = (record["intent_id"], record["request_sha256"])
                intent = store.get_intent(self.config["session_id"], record["intent_id"])
                if intent["status"] == "accepted":
                    if self.selection_path(record["intent_id"]).is_file():
                        record.update(stage="waiting_device", detail="Your tested app is saved. Waiting for the compatible device.")
                        save_private(path, record)
                        continue
                    try:
                        store.fail_intent(self.config["session_id"], record["intent_id"], "server_restarted")
                    except ConflictError:
                        pass  # An already-published package remains deliverable.
                    record.update(stage="failed", detail="Generation interrupted by server restart.")
                    save_private(path, record)
                elif intent["status"] == "published":
                    record.update(stage="ready", detail="Verified. Waiting for your device to install.")
                    save_private(path, record)
        self.resume_selected()

    def store(self):
        return RecoveryStore(self.database)

    def selection_path(self, identifier):
        return self.jobs / identifier / "selection.json"

    def publish_selected(self, identifier):
        from backend.program_runner import DEFAULT_RUNNER, _read
        selection = json.loads(self.selection_path(identifier).read_bytes())
        runner_hash = hashlib.sha256(_read(DEFAULT_RUNNER, 64 * 1024 * 1024)).hexdigest()
        with self.store() as store:
            # Store checks current intent, exact receipt and fresh compatibility
            # inside its publication transaction. Stale targets keep the result.
            envelope = store.publish_program(self.config["session_id"], identifier, selection["receipt_id"],
                                              expected_runner_sha256=runner_hash)
        self.progress(identifier, "ready", "Tested and saved. Waiting for your device to install.")
        return envelope

    def resume_selected(self):
        """Retry only durable selected work; never repeat provider generation."""
        with self.lock:
            if self.busy:
                return
            for path in self.jobs.glob("*.json"):
                record = json.loads(path.read_bytes())
                if record.get("stage") != "waiting_device":
                    continue
                try:
                    self.publish_selected(record["intent_id"])
                except CapabilityError:
                    pass
                except ConflictError:
                    self.progress(record["intent_id"], "superseded", "Replaced by a newer request.")
                except (StoreError, OSError, ValueError):
                    self.progress(record["intent_id"], "failed", "generation_failed")

    def authorized(self, authorization, role):
        expected = "Bearer " + self.config[role + "_token"]
        return type(authorization) is str and authorization.isascii() and hmac.compare_digest(authorization, expected)

    def upload(self, mime_type, data):
        if mime_type not in MEDIA_TYPES or not data or len(data) > MAX_UPLOAD:
            raise RequestError("unsupported_or_oversized_media")
        identifier = uuid.uuid4().hex
        path = self.uploads / identifier
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        save_private(self.uploads / (identifier + ".json"),
                     {"mime_type": mime_type, "sha256": hashlib.sha256(data).hexdigest(),
                      "size_bytes": len(data)})
        return {"upload_id": identifier}

    def generate(self, value):
        if type(value) is not dict or set(value) != {"prompt", "uploads", "request_id"}:
            raise RequestError("invalid_generation_request")
        prompt, identifiers, key = value["prompt"], value["uploads"], value["request_id"]
        if type(prompt) is not str or len(prompt) > 6000 or type(identifiers) is not list or len(identifiers) > MAX_ATTACHMENTS:
            raise RequestError("invalid_generation_request")
        if not prompt.strip() and not identifiers:
            raise RequestError("input_required")
        if type(key) is not str or not ID.fullmatch(key):
            raise RequestError("invalid_request_id")
        media, snapshot = [], []
        for identifier in identifiers:
            if type(identifier) is not str or not ID.fullmatch(identifier):
                raise RequestError("invalid_upload")
            try:
                metadata = json.loads((self.uploads / (identifier + ".json")).read_text())
                path = self.uploads / identifier
                if hashlib.sha256(path.read_bytes()).hexdigest() != metadata["sha256"]:
                    raise RequestError("upload_integrity_failed")
            except OSError:
                raise RequestError("upload_missing") from None
            media.append({"path": path, "mime_type": metadata["mime_type"]})
            snapshot.append(dict(metadata, upload_id=identifier))
        if sum(item["size_bytes"] for item in snapshot) > MAX_TOTAL_MEDIA:
            raise RequestError("combined_media_too_large", 413)
        frozen = json.dumps({"prompt": prompt, "media": snapshot}, sort_keys=True).encode()
        frozen_hash = hashlib.sha256(frozen).hexdigest()
        with generation_gate(self.directory), self.lock:
            if key in self.requests:
                identifier, old_hash = self.requests[key]
                if old_hash != frozen_hash:
                    raise RequestError("request_conflict", 409)
                return {"job_id": identifier}
            if self.busy:
                raise RequestError("generation_busy", 409)
            with self.store() as store:
                accept = store.accept_program_intent if self.programmable else store.accept_intent
                intent = accept(self.config["session_id"], self.config["device_id"], key, frozen)
            record_path = self.jobs / (intent["intent_id"] + ".json")
            if record_path.exists():
                return {"job_id": intent["intent_id"]}
            try:
                save_private(record_path, {"intent_id": intent["intent_id"], "request_id": key,
                                           "request_sha256": frozen_hash,
                                           "stage": "preparing" if intent["status"] == "accepted" else "failed",
                                           "detail": "Preparing your request." if intent["status"] == "accepted" else "This request could not be started. Submit a new request."})
                self.requests[key] = (intent["intent_id"], frozen_hash)
                if intent["status"] == "accepted":
                    self.busy = True
                    thread = threading.Thread(target=self._generate, args=(intent["intent_id"], prompt, media), daemon=True)
                    thread.start()
            except Exception:
                self.busy = False
                self.requests.pop(key, None)
                with self.store() as store:
                    if intent["status"] == "accepted":
                        store.fail_intent(self.config["session_id"], intent["intent_id"], "job_start_failed")
                raise RequestError("job_start_failed", 500) from None
        return {"job_id": intent["intent_id"]}

    def progress(self, identifier, stage, detail, diagnostics=None):
        path = self.jobs / (identifier + ".json")
        record = json.loads(path.read_text())
        record.update(stage=stage, detail=detail)
        if diagnostics is not None:
            record["diagnostics"] = safe_diagnostics(diagnostics)
        save_private(path, record)

    def _generate(self, identifier, prompt, media):
        try:
            if self.programmable:
                from backend.program_generation import generate_program
                generator = self.program_generator or generate_program
                generator(self.database, self.config["session_id"], identifier, self.jobs / identifier,
                          self.uploads, lambda stage, detail: self.progress(identifier, stage, detail))
                try:
                    self.publish_selected(identifier)
                except CapabilityError:
                    self.progress(identifier, "waiting_device", "Your tested app is saved. Waiting for the compatible device.")
                return
            generator = self.generator
            if generator is None:
                from backend.generator import generate_app
                generator = generate_app
            package = generator(prompt, media, lambda stage, detail: self.progress(identifier, stage, detail))
            with self.store() as store:
                store.publish(self.config["session_id"], identifier, package)
            self.progress(identifier, "ready", "Verified. Waiting for your device to install.")
        except Exception as exc:
            # Provider exceptions expose only approved codes; never log raw errors.
            code = getattr(exc, "code", "generation_failed")
            if type(code) is not str or code not in ERROR_MESSAGES:
                code = "generation_failed"
            with self.store() as store:
                try:
                    store.fail_intent(self.config["session_id"], identifier, code)
                except StoreError:
                    pass
            self.progress(identifier, "failed", code, safe_diagnostics(getattr(exc, "diagnostics", None)))
        finally:
            with self.lock:
                self.busy = False

    def status(self, identifier):
        with self.store() as store:
            # Distinguish a discarded browser job from a transient server error.
            if store._db.execute("SELECT 1 FROM intents WHERE intent_id=? AND session_id=?",
                                 (identifier, self.config["session_id"])).fetchone() is None:
                raise RequestError("job_not_found", 404)
            intent = store.get_intent(self.config["session_id"], identifier)
            desired = store.desired_for_device(self.config["device_id"])
            active = store.active_for_session(self.config["session_id"], self.config["device_id"])
            history = store.ack_history(self.config["session_id"], identifier)
            recovery = store.recovery_for_intent(self.config["session_id"], identifier)
        try:
            record = json.loads((self.jobs / (identifier + ".json")).read_text())
        except FileNotFoundError:
            record = {"intent_id": identifier, "stage": intent["status"], "detail": ""}
        if "diagnostics" in record:
            record["diagnostics"] = safe_diagnostics(record["diagnostics"])
        matching = desired is not None and desired["sequence"] == intent["sequence"]
        is_active = matching and active is not None and active["deployment_id"] == desired["deployment_id"]
        if recovery:
            detail = ("This app stopped. The previous app was restored." if recovery["recovered"] is not None
                      else "This app stopped. The device returned to its built-in app.")
            record.update(stage="recovered", detail=detail)
        elif is_active:
            record.update(stage="active", detail="Your app is running on the device.")
        elif intent["status"] in ("failed", "superseded"):
            record.update(stage=intent["status"], detail=intent["error_code"] or "Replaced by a newer request.")
        elif any(ack["status"] == "failed" for ack in history):
            record.update(stage="failed", detail="The device could not activate this app.")
        record.update(device_online=self.device_seen is not None and time.monotonic() - self.device_seen < 12,
                      deployment=desired if matching else None)
        return record


class Handler(BaseHTTPRequestHandler):
    server_version = "SketchToDevice"

    def log_message(self, *_):
        pass  # URLs, request bodies and tokens never enter access logs.

    def send(self, status, value, content_type="application/json"):
        body = value if type(value) is bytes else json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' blob:; media-src 'self' blob:; object-src 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def read_body(self, maximum):
        if self.headers.get("Transfer-Encoding"):
            raise RequestError("transfer_encoding_unsupported")
        length = self.headers.get("Content-Length", "")
        if not length.isdecimal() or not 0 < int(length) <= maximum:
            raise RequestError("invalid_body_size", 413)
        self.connection.settimeout(30)
        try:
            body = self.rfile.read(int(length))
        except TimeoutError:
            raise RequestError("upload_timeout", 408) from None
        if len(body) != int(length):
            raise RequestError("incomplete_upload")
        return body

    def dispatch(self):
        app = self.server.application
        path = urlsplit(self.path).path
        if self.command == "GET" and path in ASSETS:
            name, mime = ASSETS[path]
            return self.send(200, (ROOT / "companion" / name).read_bytes(), mime)
        role = "device" if path.startswith("/api/device/") or path.startswith("/api/apps/") else "session"
        if not app.authorized(self.headers.get("Authorization"), role):
            raise RequestError("authentication_required", 401)
        if role == "device":
            app.device_seen = time.monotonic()
        if self.command == "GET" and path == "/api/session":
            with app.store() as store:
                active = store.active_for_session(app.config["session_id"], app.config["device_id"])
            return self.send(200, {"device_id": app.config["device_id"],
                                  "device_online": app.device_seen is not None and time.monotonic() - app.device_seen < 12,
                                  "generation_busy": app.busy, "active_app": active})
        if self.command == "POST" and path == "/api/uploads":
            mime = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            return self.send(201, app.upload(mime, self.read_body(MAX_UPLOAD)))
        if self.command == "POST" and path == "/api/generate":
            return self.send(202, app.generate(json.loads(self.read_body(65536))))
        if self.command == "GET" and path.startswith("/api/jobs/"):
            identifier = path.rsplit("/", 1)[-1]
            if not re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", identifier):
                raise RequestError("invalid_job")
            return self.send(200, app.status(identifier))
        with app.store() as store:
            if self.command == "POST" and path == "/api/device/runtime":
                store.record_capabilities(app.config["device_id"], json.loads(self.read_body(8192)))
                app.resume_selected()
                return self.send(200, {"recorded": True})
            if self.command == "POST" and path == "/api/device/recovery":
                return self.send(200, store.record_recovery(app.config["device_id"], json.loads(self.read_body(4096))))
            if self.command == "GET" and path == "/api/device/desired":
                return self.send(200, {"desired": store.desired_for_device(app.config["device_id"])})
            if self.command == "POST" and path == "/api/device/ack":
                return self.send(200, store.record_ack(app.config["device_id"], json.loads(self.read_body(4096))))
            if self.command == "GET" and path.startswith("/api/apps/"):
                desired = store.desired_for_device(app.config["device_id"])
                if desired is None or path != desired["manifest"]["download_path"]:
                    raise RequestError("package_not_current", 404)
                return self.send(200, store.package_for_device(app.config["device_id"], desired["deployment_id"]))
        raise RequestError("route_not_found", 404)

    def handle_request(self):
        try:
            self.dispatch()
        except RequestError as exc:
            self.send(exc.status, {"error": exc.code})
        except ConflictError:
            self.send(409, {"error": "request_conflict"})
        except CapabilityError as exc:
            self.send(409, {"error": exc.code})
        except StoreError:
            self.send(400, {"error": "invalid_operation"})
        except (ValueError, UnicodeError):
            self.send(400, {"error": "invalid_request"})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self.send(500, {"error": "service_error"})

    do_GET = handle_request
    do_POST = handle_request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--data", type=Path, default=ROOT / "private" / "service")
    args = parser.parse_args()
    try:
        with single_instance(args.data):
            app = Application(args.data)
            server = ThreadingHTTPServer((args.host, args.port), Handler)
            server.application = app
            print("Companion service listening on port {}. Private configuration: {}".format(args.port, args.data / "demo-config.json"), flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
    except BlockingIOError:
        print("Service already running for this data directory.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
