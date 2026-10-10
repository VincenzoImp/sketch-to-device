"""Job-owned assets, real native execution and durable candidate selection.

No public HTTP endpoint or installation side effect lives here. The caller
authenticates the job and chooses the supported target before constructing it.
"""

import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import time

from backend.deployments import ConflictError, StoreError
from backend.media import MediaError
from backend.program_agent import ToolResult, _write
from backend.program_assets import convert_asset
from backend.program_runner import DEFAULT_RUNNER, RunnerError, _read, execute_program
from backend.program_store import ProgramStore
from runtime.program import (LIMITS, ValidationError, _object,
                             asset_bytes)


def _object_schema(properties, required):
    return {"type": "object", "properties": properties, "required": required,
            "additionalProperties": False}


def tool_definitions():
    """The model receives declarations for exactly these implemented services."""
    text = {"type": "string"}
    integer = {"type": "integer"}
    crop = _object_schema({key: integer for key in ("x", "y", "width", "height")},
                          ["x", "y", "width", "height"])
    crop["description"] = "Optional source crop in 0..10000 basis points, after EXIF orientation."
    event = _object_schema({"type": {"type": "string", "enum": ["tick", "pause", "resume", "pointer", "frame"]},
        "time_ms": integer, "phase": {"type": "string", "enum": ["down", "move", "up", "cancel"]},
        "x": integer, "y": integer, "name": text}, ["type"])
    event["description"] = ("Use only the fields for the chosen event type: frame has exactly type/name; "
        "pointer has exactly type/phase/x/y/time_ms; tick, pause and resume have exactly type/time_ms. "
        "A frame captures the current time and must not include time_ms or pointer fields.")
    scenario = _object_schema({"version": {"type": "integer", "enum": [1]}, "seed": integer,
        "initial_time_ms": integer, "wall_time": {"description": "null, or an object with epoch_ms integer and source estimated/synchronized"},
        "events": {"type": "array", "items": event}},
        ["version", "seed", "initial_time_ms", "wall_time", "events"])
    scenario["description"] = (
        "Exact keys: version:1, seed:uint32, initial_time_ms:nonnegative integer, "
        "wall_time:null or {epoch_ms:nonnegative integer,source:'estimated'|'synchronized'}, events:array. "
        "Events: {type:'tick'|'pause'|'resume',time_ms}; "
        "{type:'pointer',phase:'down'|'move'|'up'|'cancel',x:0..319,y:0..431,time_ms}; "
        "{type:'frame',name:unique lowercase identifier}. All times ordered, span at most120000ms. "
        "At most4096events and16frames. Include at least one frame and test requested interactions.")
    specs = [
        ("prepare_uploaded_asset", "Convert a job-owned original image into an immutable RGBA asset. "
         "Returns asset_ref for run_app and asset_id for gfx.image. No external URLs or host paths.",
         _object_schema({"upload_id": text, "asset_id": text, "width": integer, "height": integer,
                         "fit": {"type": "string", "enum": ["contain", "cover"]}, "crop": crop},
                        ["upload_id", "asset_id", "width", "height"])),
        ("run_app", "Execute freshly authored ordinary JavaScript with exact immutable packaging. "
         "Returns actual errors/screenshots and a server receipt; no installation.",
         _object_schema({"app_id": text, "name": text, "source": text,
                         "requires": {"type": "array", "items": text},
                         "asset_refs": {"type": "array", "items": text}, "scenario": scenario},
                        ["app_id", "name", "source", "requires", "asset_refs", "scenario"])),
        ("submit_app", "Select one successful server execution receipt for later publication. "
         "Do not pass source or invented receipts. This tool does not install or publish.",
         _object_schema({"receipt_id": text}, ["receipt_id"]))]
    return [{"type": "function", "name": name, "description": description, "parameters": parameters}
            for name, description, parameters in specs]


def _text(value, *, error=False, selection=None):
    return ToolResult([{"type": "text", "text": json.dumps(value, separators=(",", ":"))}], error, selection)


class ProgramBroker:
    def __init__(self, database, session_id, intent_id, job_dir, uploads, *, runner=DEFAULT_RUNNER):
        """uploads maps authorized opaque IDs to {data:bytes,mime_type:str}.

        Bind each original to the frozen request's hash before allowing tools to
        resolve it. No model-provided paths or URLs are ever opened.
        """
        self.database, self.session_id, self.intent_id = database, session_id, intent_id
        self.folder, self.runner = Path(job_dir), Path(runner)
        if self.folder.is_symlink():
            raise StoreError("Invalid job directory")
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.folder = self.folder.resolve()
        with ProgramStore(database) as store:
            request = store.job_request_bytes(session_id, intent_id)
            frozen = json.loads(request)
        self.binding = {"session_id": session_id, "intent_id": intent_id,
                        "database": str(Path(database).resolve()),
                        "request_sha256": hashlib.sha256(request).hexdigest()}
        self.binding_hash = hashlib.sha256(json.dumps(self.binding, sort_keys=True,
            separators=(",", ":")).encode()).hexdigest()
        expected = {item["upload_id"]: item for item in frozen.get("media", [])}
        if type(uploads) is not dict or set(uploads) != set(expected):
            raise StoreError("Originals do not match the frozen job")
        self.uploads = {}
        for identifier, value in uploads.items():
            raw, mime = value.get("data"), value.get("mime_type")
            metadata = expected[identifier]
            if (type(raw) is not bytes or mime != metadata["mime_type"] or len(raw) != metadata["size_bytes"]
                    or hashlib.sha256(raw).hexdigest() != metadata["sha256"]):
                raise StoreError("Originals do not match the frozen job")
            self.uploads[identifier] = {"data": raw, "mime_type": mime}
        lock = os.open(self.folder / "broker.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            binding_path = self.folder / "job-binding.json"
            if binding_path.exists():
                if json.loads(_read(binding_path, 16384)) != self.binding:
                    raise ConflictError("Job directory belongs to another request")
            else:
                if any(path.name != "broker.lock" for path in self.folder.iterdir()):
                    raise ConflictError("Unbound job directory is not empty")
                _write(binding_path, self.binding)
        finally:
            os.close(lock)

    def __call__(self, name, arguments, call_id, deadline):
        if type(call_id) is not str or not 1 <= len(call_id) <= 4096:
            raise StoreError("Invalid call identity")
        raw = json.dumps({"name": name, "arguments": arguments}, allow_nan=False,
                         sort_keys=True, separators=(",", ":")).encode()
        if len(raw) > 262144:
            raise StoreError("Tool arguments too large")
        fingerprint = hashlib.sha256(raw).hexdigest()
        key = hashlib.sha256(call_id.encode()).hexdigest()
        path = self.folder / ("broker-" + key + ".json")
        lock = os.open(self.folder / "broker.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if json.loads(_read(self.folder / "job-binding.json", 16384)) != self.binding:
                raise ConflictError("Job directory binding changed")
            with ProgramStore(self.database) as store:
                store.assert_current_program_job(self.session_id, self.intent_id)
            if path.exists():
                prior = json.loads(_read(path, 12 * 1024 * 1024))
                if prior["arguments_sha256"] != fingerprint:
                    raise ConflictError("Call identity changed arguments")
                if prior["status"] != "returned":
                    raise ConflictError("Interrupted tool call requires explicit recovery")
                return ToolResult(prior["content"], prior["is_error"], prior["selection"])
            if time.monotonic() >= deadline:
                raise RunnerError("runner_timeout")
            _write(path, {"status": "pending", "arguments_sha256": fingerprint})
            with ProgramStore(self.database) as store:
                store.assert_current_program_job(self.session_id, self.intent_id)
                try:
                    result = self._execute(store, name, arguments, deadline)
                except (ValidationError, MediaError, RunnerError, StoreError) as error:
                    detail = {"status": "rejected", "error": getattr(error, "code", None) or
                              (str(error) if isinstance(error, RunnerError) else "invalid_tool_request")}
                    if isinstance(error, ValidationError):
                        detail.update(path=error.path, message=error.message)
                        if error.path == "$.scenario" and error.code == "fields":
                            detail["required_fields"] = ["version", "seed", "initial_time_ms", "wall_time", "events"]
                            detail["example"] = {"version": 1, "seed": 1, "initial_time_ms": 0, "wall_time": None,
                                                 "events": [{"type": "frame", "name": "initial"}]}
                        elif error.path == "$.scenario.frame" and error.code == "fields":
                            detail["required_fields"] = ["type", "name"]
                            detail["example"] = {"type": "frame", "name": "initial"}
                            detail["hint"] = "A frame captures the current state; advance time with a separate tick event."
                    result = _text(detail, error=True)
            _write(path, {"status": "returned", "arguments_sha256": fingerprint,
                          "content": result.content, "is_error": result.is_error,
                          "selection": result.submission}, limit=12 * 1024 * 1024)
            return result
        finally:
            os.close(lock)

    def _execute(self, store, name, arguments, deadline):
        if name == "prepare_uploaded_asset":
            if type(arguments) is not dict or not {"upload_id", "asset_id", "width", "height"} <= set(arguments):
                raise StoreError("Missing asset arguments")
            if set(arguments) - {"upload_id", "asset_id", "width", "height", "fit", "crop"}:
                raise StoreError("Unknown asset argument")
            identifier = arguments["upload_id"]
            if type(identifier) is not str or identifier not in self.uploads:
                raise StoreError("Unknown job upload")
            original = self.uploads[identifier]
            asset, provenance = convert_asset(original["data"], original["mime_type"],
                asset_id=arguments["asset_id"], width=arguments["width"], height=arguments["height"],
                deadline=deadline, fit=arguments.get("fit", "contain"), crop=arguments.get("crop"))
            record = {"asset": asset, "provenance": provenance, "upload_id": identifier,
                      "job_binding_sha256": self.binding_hash}
            encoded = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
            reference = "asset_" + hashlib.sha256(encoded).hexdigest()
            _write(self.folder / (reference + ".json"), record)
            return _text({"asset_ref": reference, "asset_id": asset["id"], "width": asset["width"],
                          "height": asset["height"], "sha256": asset["sha256"], "format": asset["format"]})
        if name == "run_app":
            _object(arguments, {"app_id", "name", "source", "requires", "asset_refs", "scenario"}, "$.run_app")
            references = arguments["asset_refs"]
            if type(references) is not list or len(references) > LIMITS["asset_count"]:
                raise StoreError("Invalid asset list")
            assets = []
            for reference in references:
                if (type(reference) is not str or len(reference) != 70 or not reference.startswith("asset_")
                        or any(c not in "0123456789abcdef" for c in reference[6:])):
                    raise StoreError("Invalid asset reference")
                try:
                    raw = _read(self.folder / (reference + ".json"), 131072)
                except OSError:
                    raise StoreError("Unknown job asset") from None
                value = json.loads(raw)
                if hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest() != reference[6:]:
                    raise StoreError("Asset record integrity failed")
                if (value.get("job_binding_sha256") != self.binding_hash
                        or value["upload_id"] not in self.uploads):
                    raise StoreError("Asset does not belong to this job")
                original = self.uploads[value["upload_id"]]
                if (value["provenance"]["source_sha256"] != hashlib.sha256(original["data"]).hexdigest()
                        or value["provenance"]["source_mime_type"] != original["mime_type"]):
                    raise StoreError("Asset original does not match this job")
                asset_bytes(value["asset"])
                assets.append(value["asset"])
            candidate = store.prepare_candidate(self.session_id, self.intent_id, app_id=arguments["app_id"],
                name=arguments["name"], source=arguments["source"], requires=arguments["requires"], assets=assets)
            body = store.candidate_bytes(self.session_id, self.intent_id, candidate["candidate_id"])
            result = execute_program(body, arguments["scenario"], deadline=deadline, runner=self.runner)
            # A blank/no-frame scenario cannot qualify a display app for submission.
            succeeded = result.succeeded and bool(result.images) and result.report.get("committed_frames", 0) > 0
            receipt = store.record_run(self.session_id, self.intent_id, candidate["candidate_id"],
                runner_sha256=result.runner_sha256, scenario=result.scenario, result=result.report, succeeded=succeeded)
            feedback = dict(result.report, **receipt)
            if not succeeded and result.succeeded:
                feedback["error"] = "render_and_capture_a_frame"
            response = _text(feedback, error=not succeeded)
            for _, png in result.images:
                response.content.append({"type": "image", "mime_type": "image/png", "data": base64.b64encode(png).decode()})
            return response
        if name == "submit_app":
            _object(arguments, {"receipt_id"}, "$.submit_app")
            runner_hash = hashlib.sha256(_read(self.runner, 64 * 1024 * 1024)).hexdigest()
            selection = store.select_program(self.session_id, self.intent_id, arguments["receipt_id"],
                                            expected_runner_sha256=runner_hash)
            return _text({"status": "selected", **selection, "device_installed": False}, selection=selection)
        raise StoreError("Unknown tool")
