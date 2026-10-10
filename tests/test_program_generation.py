"""Real frozen-input/media/broker plumbing; provider behavior is explicitly fake."""

import base64
import hashlib
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
import wave
from unittest.mock import patch

from backend.deployments import StoreError
from backend.program_generation import generate_program, prepare_input
from backend.program_store import ProgramStore
from backend.providers import ProviderError
from scripts.probe_program_generation import original_png


class FakeSpeech:
    def transcribe(self, raw):
        with wave.open(io.BytesIO(raw)) as audio:
            assert audio.getnframes() == 2400
        return "Create an interactive reference image."


class ProgramGenerationTests(unittest.TestCase):
    def test_real_photo_normalization_and_voice_preserve_original_identity(self):
        output = io.BytesIO()
        with wave.open(output, "wb") as stream:
            stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(24000)
            stream.writeframes(bytes(4800))
        original = original_png()
        uploads = {"photo": {"data": original, "mime_type": "image/png"},
                   "speech": {"data": output.getvalue(), "mime_type": "audio/wav"}}
        stages = []
        blocks = prepare_input("A reference", uploads, lambda stage, detail: stages.append(stage),
                               deadline=time.monotonic() + 20, client=FakeSpeech())
        brief = json.loads(blocks[0]["text"])
        self.assertEqual(brief["gradium_transcripts"][0]["upload_id"], "speech")
        self.assertEqual(brief["gradium_transcripts"][0]["text"], "Create an interactive reference image.")
        images = [block for block in blocks if block["type"] == "image"]
        self.assertEqual(len(images), 1)
        self.assertTrue(base64.b64decode(images[0]["data"]).startswith(b"\xff\xd8"))
        self.assertEqual(uploads["photo"]["data"], original)
        self.assertIn("transcribing", stages)

    def test_frozen_job_runs_real_broker_and_returns_selection_without_publishing(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary); uploads = folder / "uploads"; uploads.mkdir()
            identifier = "a" * 32; original = original_png()
            (uploads / identifier).write_bytes(original)
            metadata = dict(upload_id=identifier, mime_type="image/png", size_bytes=len(original),
                            sha256=hashlib.sha256(original).hexdigest())
            database = folder / "store.sqlite"
            with ProgramStore(database) as store:
                store.bind_device("owner", "board")
                intent = store.accept_intent("owner", "board", "one", json.dumps(
                    {"prompt": "Input plumbing", "media": [metadata]}).encode())["intent_id"]
            def fake_agent(blocks, **kwargs):
                brief = json.loads(blocks[0]["text"])
                self.assertEqual(brief["uploads"][0]["upload_id"], identifier)
                broker = kwargs["execute_tool"]
                args = {"app_id": "probe", "name": "Probe", "source": "gfx.begin('#FF0000');gfx.end();",
                        "requires": ["canvas"], "asset_refs": [], "scenario": {"version": 1, "seed": 1,
                        "initial_time_ms": 0, "wall_time": None, "events": [{"type": "frame", "name": "initial"}]}}
                result = broker("run_app", args, "run", time.monotonic() + 10)
                self.assertFalse(result.is_error)
                receipt = json.loads(result.content[0]["text"])["receipt_id"]
                return broker("submit_app", {"receipt_id": receipt}, "submit", time.monotonic() + 10).submission
            selection = generate_program(database, "owner", intent, folder / "job", uploads,
                                         lambda *_: None, client=FakeSpeech(), agent=fake_agent)
            self.assertEqual(json.loads((folder / "job/selection.json").read_bytes()), selection)
            with ProgramStore(database) as store:
                self.assertIsNone(store.desired_for_device("board"))
            timing = json.loads((folder / "job/timing.json").read_bytes())
            self.assertEqual(timing["status"], "selected")
            self.assertEqual(timing["compile_ms"], 0)
            (uploads / identifier).write_bytes(original + b"changed")
            with patch("backend.program_generation.ProviderClient") as provider:
                with self.assertRaises(StoreError):
                    generate_program(database, "owner", intent, folder / "tampered", uploads, lambda *_: None)
                provider.assert_not_called()
            timing = json.loads((folder / "tampered/timing.json").read_bytes())
            self.assertEqual(timing["failed_phase"], "input_preparation")
            self.assertEqual(timing["error_code"], "generation_failed")

    def test_failed_managed_time_is_recorded_and_superseded_input_never_starts_agent(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary); database = folder / "store.sqlite"
            request = json.dumps({"prompt": "Input plumbing", "media": []}).encode()
            with ProgramStore(database) as store:
                store.bind_device("owner", "board")
                intent = store.accept_intent("owner", "board", "one", request)["intent_id"]
            clock = [0]
            def prepared(*args, **kwargs):
                clock[0] = 2
                return [{"type": "text", "text": "prepared"}]
            def failed(*args, **kwargs):
                clock[0] = 14
                raise ProviderError("network")
            with patch("backend.program_generation.time.monotonic", side_effect=lambda: clock[0]), \
                    patch("backend.program_generation.prepare_input", side_effect=prepared):
                with self.assertRaises(ProviderError):
                    generate_program(database, "owner", intent, folder / "failed", folder,
                                     lambda *_: None, client=FakeSpeech(), agent=failed)
            timing = json.loads((folder / "failed/timing.json").read_bytes())
            self.assertEqual(timing["input_preparation_ms"], 2000)
            self.assertEqual(timing["managed_generation_ms"], 12000)
            self.assertEqual(timing["total_ms"], 14000)
            self.assertEqual(timing["error_code"], "network")
            def superseded(*args, **kwargs):
                with ProgramStore(database) as store:
                    store.accept_intent("owner", "board", "two", request)
                return [{"type": "text", "text": "prepared"}]
            with patch("backend.program_generation.prepare_input", side_effect=superseded), \
                    patch("backend.program_generation.run_program_agent") as agent:
                with self.assertRaises(StoreError):
                    generate_program(database, "owner", intent, folder / "superseded", folder,
                                     lambda *_: None, client=FakeSpeech(), agent=agent)
                agent.assert_not_called()


if __name__ == "__main__":
    unittest.main()
