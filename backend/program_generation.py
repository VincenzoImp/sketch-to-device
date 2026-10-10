"""Frozen multimodal input to a managed-authored, tested program selection.

This boundary does not publish. Capability-aware orchestration publishes the
selected receipt later without regenerating or rewriting its candidate bytes.
"""

import base64
import json
from pathlib import Path
import time

from backend.generator import _convert, _snapshot
from backend.deployments import ConflictError
from backend.media import normalize_photo, MediaError
from backend.program_agent import run_program_agent, _write
from backend.program_broker import ProgramBroker, tool_definitions
from backend.program_runner import DEFAULT_RUNNER
from backend.program_store import ProgramStore
from backend.providers import ProviderClient, ProviderError, remaining, ERROR_MESSAGES


def prepare_input(prompt, originals, progress, *, deadline, client, check_active=lambda: None):
    """Perception copies and Gradium speech; original bytes stay broker-owned."""
    progress("understanding", "Reading your references and preparing the request.")
    content, transcripts, inventory = [], [], []
    for upload_id, item in originals.items():
        remaining(deadline)
        check_active()
        raw, mime = item["data"], item["mime_type"]
        inventory.append({"upload_id": upload_id, "mime_type": mime,
                          "available_as_image_asset": mime.startswith("image/")})
        if mime.startswith("image/"):
            try:
                image = normalize_photo(raw, mime, deadline)
            except MediaError as error:
                raise ProviderError(error.code) from None
            content.extend([{"type": "text", "text": "Perception copy of original upload " + upload_id},
                            {"type": "image", "mime_type": "image/jpeg", "data": base64.b64encode(image).decode()}])
        else:
            wav, image = _convert(raw, mime, deadline)
            if wav:
                check_active()
                progress("transcribing", "Gradium is transcribing your recording.")
                transcripts.append({"upload_id": upload_id, "text": client.transcribe(wav)})
            if image:
                content.extend([{"type": "text", "text": "Midpoint video frame from upload " + upload_id},
                                {"type": "image", "mime_type": "image/jpeg", "data": base64.b64encode(image).decode()}])
    remaining(deadline)
    check_active()
    content.insert(0, {"type": "text", "text": json.dumps({"user_request": prompt,
        "gradium_transcripts": transcripts, "uploads": inventory,
        "reference_note": "Images are perception copies; use original upload IDs for assets. "
                          "Videos provide one midpoint frame and available speech, not their complete motion."})})
    return content


def generate_program(database, session_id, intent_id, job_dir, uploads_dir, progress,
                     *, client=None, runner=DEFAULT_RUNNER, agent=run_program_agent,
                     stop_requested=lambda: False):
    """Read only the already frozen request and authorized opaque upload IDs.

    Input processing has a90second wall-time budget. Managed coding then has its
    own600second ceiling; phase timings are job-local rather than a shared file.
    """
    started = time.monotonic()
    folder = Path(job_dir)
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    timing = {"status": "preparing", "input_preparation_ms": 0, "managed_generation_ms": 0,
              "compile_ms": 0, "compilation_basis": "JavaScript is interpreted; firmware is not compiled per app."}
    phase, changed = "input_preparation_ms", started
    def check_active():
        if stop_requested():
            raise ProviderError("generation_stopped")
        try:
            with ProgramStore(database) as store:
                store.assert_current_program_job(session_id, intent_id)
        except ConflictError:
            raise ProviderError("generation_superseded") from None
    try:
        check_active()
        with ProgramStore(database) as store:
            frozen = json.loads(store.job_request_bytes(session_id, intent_id))
        metadata = frozen["media"]
        # Upload IDs originate from the authenticated service, never model paths.
        if any(type(item["upload_id"]) is not str or len(item["upload_id"]) != 32
               or any(c not in "0123456789abcdef" for c in item["upload_id"]) for item in metadata):
            raise ProviderError("input")
        prompt, snapshots = _snapshot(frozen["prompt"], [
            {"path": Path(uploads_dir) / item["upload_id"], "mime_type": item["mime_type"]} for item in metadata])
        originals = {item["upload_id"]: {"mime_type": mime, "data": raw}
                     for item, (mime, raw) in zip(metadata, snapshots)}
        broker = ProgramBroker(database, session_id, intent_id, folder / "tools", originals, runner=runner)
        deadline = started + 90
        client = client or ProviderClient(deadline)
        client.deadline = deadline
        content = prepare_input(prompt, originals, progress, deadline=deadline, client=client,
                                check_active=check_active)
        check_active()
        prepared = time.monotonic()
        timing["input_preparation_ms"] = round((prepared - started) * 1000)
        phase, changed = "managed_generation_ms", prepared
        selection = agent(content, job_dir=folder / "agent", tool_definitions=tool_definitions(),
                          execute_tool=broker, progress=progress, client=client, check_active=check_active)
        check_active()
        timing.update(status="selected", package_sha256=selection["sha256"])
        _write(folder / "selection.json", selection)
        return selection
    except BaseException as error:
        timing["status"] = "failed"
        code = getattr(error, "code", "generation_failed")
        timing["error_code"] = code if type(code) is str and code in ERROR_MESSAGES else "generation_failed"
        timing["failed_phase"] = phase.removesuffix("_ms")
        raise
    finally:
        finished = time.monotonic()
        timing[phase] = round((finished - changed) * 1000)
        timing["total_ms"] = round((finished - started) * 1000)
        _write(folder / "timing.json", timing)
