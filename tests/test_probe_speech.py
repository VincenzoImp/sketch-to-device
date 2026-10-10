import contextlib
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
import wave

from backend import providers
from scripts import probe_speech


def audio():
    output = io.BytesIO()
    with wave.open(output, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(24000)
        stream.writeframes(b"\0\0" * 2400)
    return output.getvalue()


def response(text):
    return (json.dumps({"type": "text", "text": text}) + '\n' +
            json.dumps({"type": "end_of_stream"}) + '\n').encode()


class SpeechComparisonTests(unittest.TestCase):
    def test_inert_without_both_explicit_flags(self):
        with patch.object(probe_speech, "compare", side_effect=AssertionError("must be inert")):
            for arguments in ([], ["--live"], ["--last-failed"]):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(probe_speech.main(arguments), 0)
                self.assertEqual(json.loads(output.getvalue())["requests_sent"], 0)

    def test_same_audio_fixed_profiles_private_transcripts_and_no_claim_of_accuracy(self):
        raw = audio()
        calls = []
        def send(provider, key, path, body, content_type, deadline, limit):
            self.assertEqual((provider, key, body, content_type, limit),
                             ("gradium", "test-private-key", raw, "audio/wav", 131072))
            self.assertGreater(deadline, time.monotonic())
            self.assertLessEqual(deadline - time.monotonic(), 30)
            calls.append(json.loads(parse_qs(urlsplit(path).query)["json_config"][0]))
            return response("Private title: 15 second top game score" if len(calls) == 1 else
                            "Private title: 15 second tap game score countdown")
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            private = folder / "speech-comparison.json"
            private.write_text("old")
            private.chmod(0o644)
            with patch.object(probe_speech, "frozen_input", return_value=("", [("audio/wav", raw)])), \
                    patch.object(probe_speech, "load_keys", return_value={"gradium": "test-private-key"}), \
                    patch.object(probe_speech, "request", side_effect=send):
                result = probe_speech.compare(folder, folder)
            self.assertEqual(calls, [providers.STT_CONFIGS["default"], providers.STT_CONFIGS["runtime_context"]])
            self.assertFalse(result["profiles"][0]["requirements"]["tap_game"])
            self.assertTrue(result["profiles"][1]["requirements"]["tap_game"])
            self.assertNotIn("Private title", json.dumps(result))
            self.assertNotIn("test-private-key", private.read_text())
            self.assertEqual(private.stat().st_mode & 0o777, 0o600)
            self.assertIn("Private title", private.read_text())
            self.assertFalse(result["accuracy_verified"])
            self.assertFalse(result["production_changed"])
            self.assertFalse(result["device_installed"])

    def test_ambiguous_recordings_fail_before_keys_or_requests(self):
        raw = audio()
        with patch.object(probe_speech, "frozen_input", return_value=("", [("audio/wav", raw)] * 2)), \
                patch.object(probe_speech, "load_keys", side_effect=AssertionError("no key access")):
            with self.assertRaises(probe_speech.ReplayError):
                probe_speech.compare(Path("unused"), Path("unused"))

    def test_out_of_range_recognition_is_retained_and_does_not_abort_comparison(self):
        raw = audio()
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            with patch.object(probe_speech, "frozen_input", return_value=("", [("audio/wav", raw)])), \
                    patch.object(probe_speech, "load_keys", return_value={"gradium": "test-key"}), \
                    patch.object(probe_speech, "request", side_effect=[response("create a 9999 second timer"),
                                                                       response("create a 15 second timer")]) as send:
                result = probe_speech.compare(folder, folder)
            self.assertEqual(send.call_count, 2)
            self.assertEqual(result["profiles"][0]["requirements_error"], "outside_runtime_limits")
            self.assertEqual(result["profiles"][1]["requirements"]["duration_seconds"], 15)
            self.assertIn("9999 second", (folder / "speech-comparison.json").read_text())

    def test_unknown_routes_fail_before_network_and_production_uses_measured_context(self):
        raw = audio()
        with patch.object(providers, "network_preflight", side_effect=AssertionError("no network")):
            for path in (providers.STT_PATHS["runtime_context"] + "&host=attacker", "/api/post/speech/asr"):
                with self.assertRaises(providers.ProviderError):
                    providers.request("gradium", "test-key", path, raw, "audio/wav", time.monotonic() + 1)
        client = object.__new__(providers.ProviderClient)
        client.keys = {"gradium": "test-key"}
        client.deadline = time.monotonic() + 5
        with patch.object(providers, "request", return_value=response("timer")) as send:
            self.assertEqual(client.transcribe(raw), "timer")
        self.assertEqual(send.call_args.args[2], providers.STT_PATHS["runtime_context"])


if __name__ == "__main__":
    unittest.main()
