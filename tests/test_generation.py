"""Offline protocol and behavior checks; no provider or physical-device claims."""

import base64
import contextlib
import hashlib
import io
import json
import shlex
import stat
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
import wave

from backend import generator, providers


ROOT = Path(__file__).resolve().parents[1]
RAW = (ROOT / "contracts/fixtures/tap-sprint.json").read_bytes()


def audio(seconds=0.1):
    output = io.BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(24000)
        target.writeframes(b"\x00\x00" * int(seconds * 24000))
    return output.getvalue()


def completed(raw=RAW, index=1, trace=True):
    result = {"id": "interaction_" + str(index), "status": "completed", "agent": generator.AGENT,
              "environment_id": "environment_1", "steps": []}
    if trace:
        result["steps"] = [
            {"type": "code_execution_call", "id": "call_1", "arguments":
             {"language": "python", "code": "subprocess.run(['python3', '/workspace/trusted_check.py'])"}},
            {"type": "code_execution_result", "call_id": "call_1", "is_error": False,
             "result": "VALIDATED_APP " + hashlib.sha256(raw).hexdigest() + "\n"}]
    return result


class FakeClient:
    """Protocol fixture, not a provider emulator or live proof."""
    def __init__(self, outcomes=None, artifacts=None):
        self.outcomes = list(outcomes or [completed()])
        self.artifacts = list(artifacts or [RAW])
        self.payloads, self.calls, self.speech = [], [], []
        self.deadline = time.monotonic() + 180

    def interaction(self, payload):
        self.payloads.append(payload)
        return self.outcomes.pop(0)

    def google(self, method, path, payload=None, raw_response=False):
        self.calls.append((method, path))
        if path.endswith("?recursive=true"):
            return {"files": [{"type": "FILE", "path": "workspace/out/app.json"}]}
        if raw_response:
            return self.artifacts.pop(0)
        if path.endswith("/cancel"):
            return {"id": "interaction_1", "status": "cancelled"}
        return completed()

    def transcribe(self, raw):
        self.speech.append(raw)
        return "Create a ten-second tap game."


class GenerationTests(unittest.TestCase):
    def generate(self, client, prompt="Create a ten-second tap game", media=None):
        progress = []
        with patch.object(generator, "ProviderClient", return_value=client), patch.object(generator, "_record_terminal"):
            result = generator.generate_app(prompt, media or [], lambda stage, detail: progress.append((stage, detail)))
        return result, progress

    def test_completed_requires_download_exact_hash_and_trusted_behavior(self):
        client = FakeClient()
        result, progress = self.generate(client)
        self.assertEqual(result, RAW)
        self.assertEqual(progress[-1][0], "ready")
        payload = client.payloads[0]
        self.assertEqual(payload["agent"], generator.AGENT)
        self.assertEqual(payload["agent_config"]["max_total_tokens"], 50000)
        self.assertEqual(payload["environment"]["network"], "disabled")
        self.assertEqual(payload["tools"], [{"type": "code_execution"}])
        sources = payload["environment"]["sources"]
        targets = [source["target"] for source in sources]
        self.assertIn("/workspace/contracts/runtime-capabilities.json", targets)
        self.assertIn("/workspace/runtime/validation.py", targets)
        self.assertNotIn(".env", " ".join(targets))
        self.assertTrue(any(path.endswith("workspace/out/app.json?alt=media") for _, path in client.calls))

    def test_downloaded_invalid_source_repairs_and_revalidates_new_exact_bytes(self):
        invalid = json.loads(RAW)
        invalid["version"] = 2
        raw = json.dumps(invalid).encode()
        client = FakeClient([completed(raw), completed(index=2)], [raw, RAW])
        result, progress = self.generate(client)
        self.assertEqual(result, RAW)
        self.assertEqual(len(client.payloads), 2)
        self.assertEqual(client.payloads[1]["environment"], "environment_1")
        self.assertEqual(client.payloads[1]["previous_interaction_id"], "interaction_1")
        self.assertIn("repairing", [stage for stage, _ in progress])

    def test_final_prose_and_wrong_hash_never_replace_execution_evidence(self):
        for kind in ("prose", "wrong_hash", "wrong_call"):
            response = completed(trace=kind != "prose")
            response["outputs"] = [{"type": "text", "text": "Validation passed"}]
            if kind == "wrong_hash":
                response["steps"][1]["result"] = "VALIDATED_APP " + "0" * 64
            if kind == "wrong_call":
                response["steps"][1]["call_id"] = "unpaired"
            client = FakeClient([response] * 3, [RAW] * 3)
            with self.subTest(kind=kind), self.assertRaises(generator.GenerationError) as caught:
                self.generate(client)
            self.assertEqual(caught.exception.code, "repair_limit")
            self.assertEqual(len(client.payloads), 3)

    def test_real_runtime_rejects_wrong_score_despite_successful_remote_marker(self):
        app = json.loads(RAW)
        tap = next(widget for screen in app["screens"] for widget in screen["widgets"] if widget["id"] == "tap")
        tap["on_press"][0]["amount"] = 2
        raw = json.dumps(app).encode()
        client = FakeClient([completed(raw)] * 3, [raw] * 3)
        with self.assertRaises(generator.GenerationError) as caught:
            self.generate(client)
        self.assertEqual(caught.exception.code, "repair_limit")

    def test_incomplete_is_failure_without_download_or_automatic_escalation(self):
        client = FakeClient([{"id": "interaction_1", "status": "incomplete", "environment_id": "environment_1",
                              "usage": {"total_input_tokens": 31999, "total_output_tokens": 200,
                                        "total_tokens": 33000, "private_metadata": "PRIVATE"},
                              "steps": [{"type": "code_execution_call", "arguments": {"code": "PRIVATE"}}],
                              "incomplete_details": {"reason": "PRIVATE"}}])
        with self.assertRaises(generator.GenerationError) as caught:
            self.generate(client)
        self.assertEqual(caught.exception.code, "provider_response")
        self.assertEqual(len(client.payloads), 1)
        self.assertEqual(client.calls, [])
        diagnostic = caught.exception.diagnostics
        self.assertEqual(diagnostic["reason"], "interaction_not_completed")
        self.assertEqual(diagnostic["interaction_status"], "incomplete")
        self.assertEqual(diagnostic["usage"]["total_tokens"], 33000)
        self.assertEqual(diagnostic["step_counts"]["code_execution_call"], 1)
        self.assertEqual(diagnostic["attempt"], 1)
        self.assertEqual(diagnostic["token_budget"], 50000)
        self.assertNotIn("PRIVATE", json.dumps(diagnostic))

    def test_incomplete_download_requires_actual_checker_hash_and_keeps_terminal_status(self):
        response = completed()
        response["status"] = "incomplete"
        response["usage"] = {"total_tokens": 63957, "total_cached_tokens": 5946}
        client, progress = FakeClient([response]), []
        with patch.object(generator, "ProviderClient", return_value=client), patch.object(generator, "_record_terminal") as record:
            raw = generator.generate_app("Create a ten-second tap game", [], lambda stage, detail: progress.append((stage, detail)))
        self.assertEqual(raw, RAW)
        self.assertEqual(record.call_args.args[0]["status"], "incomplete")
        self.assertEqual(response["status"], "incomplete")
        self.assertEqual(len(client.payloads), 1)
        self.assertEqual(len(client.calls), 2)
        self.assertTrue(all(method == "GET" for method, _ in client.calls))
        self.assertEqual(progress[-1][0], "ready")
        self.assertTrue(any(stage == "validating" and "stopped" in detail for stage, detail in progress))

    def test_incomplete_claims_and_other_terminal_states_never_start_download(self):
        for kind in ("prose", "unpaired", "errored", "malformed_hash", "failed", "cancelled"):
            response = completed(trace=kind != "prose")
            response["status"] = kind if kind in {"failed", "cancelled"} else "incomplete"
            response["outputs"] = [{"type": "text", "text": "VALIDATED_APP " + hashlib.sha256(RAW).hexdigest()}]
            if kind == "unpaired":
                response["steps"][1]["call_id"] = "wrong_call"
            elif kind == "errored":
                response["steps"][1]["is_error"] = True
            elif kind == "malformed_hash":
                response["steps"][1]["result"] = "VALIDATED_APP " + "not-a-sha256"
            client = FakeClient([response])
            with self.subTest(kind=kind), self.assertRaises(generator.GenerationError):
                self.generate(client)
            self.assertEqual(client.calls, [])
            self.assertEqual(len(client.payloads), 1)

    def test_incomplete_invalid_or_mismatched_download_fails_without_repair(self):
        wrong_score = json.loads(RAW)
        tap = next(widget for screen in wrong_score["screens"] for widget in screen["widgets"] if widget["id"] == "tap")
        tap["on_press"][0]["amount"] = 2
        for kind, artifact in (("hash", RAW), ("behavior", json.dumps(wrong_score).encode()), ("schema", b'{}')):
            response = completed(artifact)
            response["status"] = "incomplete"
            if kind == "hash":
                response["steps"][1]["result"] = "VALIDATED_APP " + "0" * 64
            client = FakeClient([response], [artifact])
            with self.subTest(kind=kind), self.assertRaises(generator.GenerationError) as caught:
                self.generate(client)
            self.assertEqual(caught.exception.code, "provider_response")
            self.assertEqual(caught.exception.diagnostics["interaction_status"], "incomplete")
            self.assertEqual(caught.exception.diagnostics["reason"], "execution_evidence_missing" if kind == "hash" else "validation_failed")
            self.assertEqual(len(client.payloads), 1)
            self.assertEqual(len(client.calls), 2)

    def test_incomplete_missing_environment_file_is_failure_not_trace_reconstruction(self):
        response = completed()
        response["status"] = "incomplete"
        client = FakeClient([response])
        client.google = Mock(return_value={"files": []})
        with self.assertRaises(generator.GenerationError) as caught:
            self.generate(client)
        self.assertEqual(caught.exception.diagnostics["reason"], "artifact_not_found")
        self.assertEqual(caught.exception.diagnostics["interaction_status"], "incomplete")
        self.assertEqual(len(client.payloads), 1)
        client.google.assert_called_once_with("GET", "/v1beta/environments/environment_1/files?recursive=true")

    def test_budget_reason_uses_validated_noncached_usage_and_actual_request_cap(self):
        response = {"id": "interaction_1", "status": "incomplete",
                    "usage": {"total_tokens": 137641, "total_cached_tokens": 103693}, "steps": []}
        # Reproduce the observed replay against its historical cap, not today's changed cap.
        with patch.object(generator, "TOKEN_BUDGET", 32768), self.assertRaises(generator.GenerationError) as caught:
            self.generate(FakeClient([response]))
        self.assertEqual(caught.exception.diagnostics["effective_tokens"], 33948)
        self.assertEqual(caught.exception.diagnostics["reason"], "token_budget_exhausted")
        with self.assertRaises(generator.GenerationError) as caught:
            self.generate(FakeClient([response]))
        self.assertEqual(caught.exception.diagnostics["reason"], "interaction_not_completed")
        for total, cached in ((True, 0), (100, False), (100, 101), (-1, 0), (10**13, 0), (100, "PRIVATE")):
            diagnostic = generator._interaction_diagnostics({"status": "incomplete", "usage":
                {"total_tokens": total, "total_cached_tokens": cached}})
            self.assertNotIn("effective_tokens", diagnostic)

    def test_bounded_guide_and_quoted_write_execute_with_real_mounted_checker(self):
        requirements = {"tap_game": True, "duration_seconds": 15}
        sources = generator._sources(requirements)
        authoring = next(source["content"] for source in sources if source["target"].endswith("/authoring.txt"))
        for name in generator.PUBLIC_FILES:
            mounted = next(source["content"] for source in sources if source["target"] == "/workspace/" + name)
            self.assertEqual(mounted, (ROOT / name).read_text())
        self.assertLessEqual(len(authoring.encode()), 7500)
        self.assertLessEqual(max(map(len, authoring.splitlines())), 500)
        self.assertFalse(any(source["target"] == "/workspace/out/app.json" for source in sources))
        app = json.loads(RAW)
        app["name"] = "Fifteen Second Dash"
        app["state"]["enabled"] = False
        app["screens"][0]["widgets"][0]["text"] = "$defs stays literal"
        for screen in app["screens"]:
            for widget in screen["widgets"]:
                if widget["type"] == "timer":
                    widget["duration_seconds"] = 15
        changed = (json.dumps(app, indent=2) + "\n").encode()
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            for source in sources:
                target = workspace / source["target"].removeprefix("/workspace/")
                target.parent.mkdir(parents=True, exist_ok=True)
                # Relocate only the two fixed data paths; execute the actual mounted trusted checker.
                content = source["content"].replace("/workspace/", str(workspace) + "/") if target.name == "trusted_check.py" else source["content"]
                target.write_text(content)
            target = workspace / "out/app.json"
            read = subprocess.run(["/bin/bash", "-c", generator.READ_COMMAND.replace("/workspace/", str(workspace) + "/")],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
            self.assertEqual(read.returncode, 0)
            self.assertEqual(read.stdout, authoring.encode())
            command = generator.WRITE_COMMAND.replace("/workspace/", str(workspace) + "/")
            command = command.replace("python3 ", shlex.quote(sys.executable) + " -B ")
            environment = {"PATH": "/usr/bin:/bin", "defs": "WRONG_SHELL_EXPANSION"}
            passed = subprocess.run(["/bin/bash", "-c", command.replace("REPLACE_WITH_REQUEST_SPECIFIC_JSON", changed.decode().rstrip("\n"))],
                                    cwd=workspace, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
            self.assertEqual(passed.returncode, 0)
            self.assertEqual(passed.stdout.decode().strip(), "VALIDATED_APP " + hashlib.sha256(changed).hexdigest())
            self.assertEqual(target.read_bytes(), changed)
            self.assertFalse(json.loads(target.read_bytes())["state"]["enabled"])
            self.assertEqual(json.loads(target.read_bytes())["screens"][0]["widgets"][0]["text"], "$defs stays literal")
            tap = next(widget for screen in app["screens"] for widget in screen["widgets"] if widget["id"] == "tap")
            tap["on_press"][0]["amount"] = 2
            failed = subprocess.run(["/bin/bash", "-c", command.replace("REPLACE_WITH_REQUEST_SPECIFIC_JSON", json.dumps(app, indent=2))],
                                    cwd=workspace, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
            self.assertNotEqual(failed.returncode, 0)
            self.assertNotIn(b"VALIDATED_APP", failed.stdout)

    def test_terminal_trace_is_bounded_private_and_omits_thoughts_headers(self):
        response = completed()
        response["headers"] = {"x-api-key": "HEADER_SECRET"}
        response["steps"].extend([{"type": "model_thought", "text": "HIDDEN_THOUGHT"},
                                  {"type": "model_output", "text": "PRIVATE_PROSE"},
                                  {"type": "function_call", "id": "f", "name": "read_file",
                                   "arguments": {"path": "/workspace/authoring.json"}}])
        with tempfile.TemporaryDirectory() as temporary, patch.object(generator, "ROOT", Path(temporary)):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertTrue(generator._record_terminal(response, ["PRIVATE_TRANSCRIPT"], {"tap_game": True}, 1))
            path = Path(temporary) / "private/provider/managed-last-execution.json"
            trace = json.loads(path.read_text())
            self.assertEqual(trace["transcripts"], ["PRIVATE_TRANSCRIPT"])
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(output.getvalue(), "")
            self.assertEqual({step["type"] for step in trace["steps"]},
                             {"code_execution_call", "code_execution_result", "function_call"})
            for omitted in ("HEADER_SECRET", "HIDDEN_THOUGHT", "PRIVATE_PROSE"):
                self.assertNotIn(omitted, path.read_text())
            response["steps"][1]["result"] = "x" * (generator.MAX_TERMINAL_TRACE + 1)
            self.assertTrue(generator._record_terminal(response, ["PRIVATE_TRANSCRIPT"], {}, 1))
            self.assertLess(path.stat().st_size, generator.MAX_TERMINAL_TRACE)
            self.assertEqual(json.loads(path.read_text())["trace_omitted"], "size_limit")
            self.assertNotIn("PRIVATE_TRANSCRIPT", path.read_text())

    def test_missing_artifact_is_distinguished_from_terminal_incomplete(self):
        client = FakeClient()
        client.google = Mock(return_value={"files": [{"type": "FILE", "path": "PRIVATE_OTHER_FILE"}]})
        with self.assertRaises(generator.GenerationError) as caught:
            self.generate(client)
        diagnostic = caught.exception.diagnostics
        self.assertEqual(diagnostic["reason"], "artifact_not_found")
        self.assertEqual(diagnostic["phase"], "list_artifact")
        self.assertEqual(diagnostic["artifact_matches"], 0)
        self.assertEqual(diagnostic["interaction_status"], "completed")
        self.assertNotIn("PRIVATE", json.dumps(diagnostic))

    def test_cli_sanitizes_all_diagnostics_without_prompt_ids_or_raw_errors(self):
        failure = providers.ProviderError("provider_response")
        failure.diagnostics = {"phase": "poll", "interaction_status": "incomplete", "reason": "PRIVATE",
                               "usage": {"total_tokens": 100, "total_input_tokens": True,
                                         "total_cached_tokens": -1, "total_output_tokens": 10**13,
                                         "total_thought_tokens": "PRIVATE", "private": "PRIVATE"},
                               "step_counts": {"code_execution_call": 2, "model_output": False, "PRIVATE": 3},
                               "interaction_id": "PRIVATE", "prompt": "PRIVATE", "raw_error": "PRIVATE"}
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(generator, "ROOT", Path(temporary)), patch.object(generator, "generate_app", side_effect=failure), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(generator.main(["--live"]), 1)
            result_path = Path(temporary) / "artifacts/generation-last-result.json"
            self.assertEqual(json.loads(result_path.read_text()), json.loads(output.getvalue()))
            self.assertEqual(stat.S_IMODE(result_path.stat().st_mode), 0o600)
            self.assertIn("observed_at_utc", json.loads(result_path.read_text()))
        rendered = output.getvalue()
        diagnostic = json.loads(rendered)["diagnostics"]
        self.assertNotIn("PRIVATE", rendered)
        self.assertEqual(diagnostic["usage"], {"total_tokens": 100})
        self.assertEqual(diagnostic["step_counts"], {"code_execution_call": 2})

    def test_poll_failure_attempts_one_bounded_cancellation(self):
        client = FakeClient([{"id": "interaction_1", "status": "in_progress"}])
        original = client.google
        def google(method, path, **kwargs):
            if not path.endswith("/cancel"):
                raise providers.ProviderError("deadline")
            return original(method, path, **kwargs)
        client.google = google
        with patch.object(generator.time, "sleep"), self.assertRaises(generator.GenerationError) as caught:
            self.generate(client)
        self.assertEqual(caught.exception.code, "deadline")
        self.assertEqual(client.calls, [("POST", "/v1beta/interactions/interaction_1/cancel")])

    def test_actual_audio_route_uses_gradium_transcript_and_image_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            speech, photo = Path(temporary) / "speech.wav", Path(temporary) / "sketch.png"
            speech.write_bytes(audio())
            photo.write_bytes(b"\x89PNG\r\n\x1a\nfixed-test-image")
            client = FakeClient()
            result, progress = self.generate(client, "", [{"path": speech, "mime_type": "audio/wav"},
                                                           {"path": photo, "mime_type": "image/png"}])
            self.assertEqual(result, RAW)
            self.assertEqual(client.speech, [speech.read_bytes()])
            self.assertIn("transcribing", [stage for stage, _ in progress])
            content = client.payloads[0]["input"]
            self.assertIn("Gradium transcript", content[0]["text"])
            self.assertEqual(base64.b64decode(content[1]["data"]), photo.read_bytes())

    def test_freezes_media_before_client_and_rejects_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "image.png"
            original = b"\x89PNG\r\n\x1a\noriginal"
            source.write_bytes(original)
            client = FakeClient()
            def factory(deadline):
                source.write_bytes(b"changed")
                return client
            with patch.object(generator, "ProviderClient", side_effect=factory), patch.object(generator, "_record_terminal"):
                generator.generate_app("ten-second tap game", [{"path": source, "mime_type": "image/png"}], lambda *args: None)
            self.assertEqual(base64.b64decode(client.payloads[0]["input"][1]["data"]), original)
            link = Path(temporary) / "link.png"
            link.symlink_to(source)
            with self.assertRaises(generator.GenerationError):
                generator._snapshot("request", [{"path": link, "mime_type": "image/png"}])

    def test_duration_enforcement_and_non_game_runtime_checks(self):
        self.assertEqual(generator.requirements_for("a five-minute focus timer")["duration_seconds"], 300)
        with self.assertRaises(ValueError):
            generator.verify_behavior(RAW, {"tap_game": True, "duration_seconds": 15})
        raw = (ROOT / "contracts/fixtures/focus-timer.json").read_bytes()
        report = generator.verify_behavior(raw, {"tap_game": False, "duration_seconds": None})
        self.assertGreater(report["checks"], 1)
        self.assertEqual(report["coverage"], "bounded_runtime_controls_and_timers")

    def test_browser_webm_missing_duration_is_measured_then_transcoded(self):
        calls = []
        def process(argv, deadline):
            calls.append(argv)
            if "-show_entries" in argv:
                return b'{"format":{},"streams":[{"codec_type":"audio"}]}'
            if "-progress" in argv:
                return b'out_time_us=100000\nprogress=end\n'
            Path(argv[-1]).write_bytes(audio())
            return b""
        with patch.object(generator.shutil, "which", side_effect=lambda tool: "/trusted/" + tool), patch.object(generator, "_process", side_effect=process):
            wav, image = generator._convert(b"\x1a\x45\xdf\xa3test", "audio/webm", time.monotonic() + 30)
        self.assertEqual(wav, audio())
        self.assertIsNone(image)
        self.assertEqual(len(calls), 3)
        self.assertTrue(all("file,pipe" in call for call in calls))
        self.assertEqual(calls[-1][calls[-1].index("-t") + 1], "31")

    def test_overlong_recording_rejected_before_transcription(self):
        with self.assertRaises(providers.ProviderError) as caught:
            providers.wav_duration(audio(30.001))
        self.assertEqual(caught.exception.code, "media_limit")
        metadata = b'{"format":{"duration":"30.001"},"streams":[{"codec_type":"audio"}]}'
        measured = b'out_time_us=30001000\nprogress=end\n'
        with patch.object(generator.shutil, "which", return_value="/trusted/tool"), patch.object(generator, "_process", side_effect=[metadata, measured]) as process:
            with self.assertRaises(generator.GenerationError) as caught:
                generator._convert(b"input", "audio/webm", time.monotonic() + 30)
        self.assertEqual(caught.exception.code, "media_limit")
        self.assertEqual(process.call_count, 2)

    def test_real_webm_codec_padding_does_not_extend_recording_limit(self):
        ffmpeg = generator._media_tool("ffmpeg")
        if not ffmpeg or not generator._media_tool("ffprobe"):
            self.skipTest("FFmpeg and FFprobe are required for the real media regression.")
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "recording.webm"
            for seconds in (30, 30.001, 31):
                for seekable in (True, False):
                    with self.subTest(seconds=seconds, seekable=seekable):
                        argv = [ffmpeg, "-nostdin", "-v", "error", "-y", "-f", "lavfi",
                                "-i", "sine=frequency=440:sample_rate=48000", "-t", str(seconds),
                                "-c:a", "libopus", "-f", "webm", str(target) if seekable else "pipe:1"]
                        encoded = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                                 stderr=subprocess.PIPE, check=True, timeout=20)
                        raw = target.read_bytes() if seekable else encoded.stdout
                        if seconds == 30:
                            wav, image = generator._convert(raw, "audio/webm", time.monotonic() + 20)
                            self.assertEqual(providers.wav_duration(wav), 30)
                            self.assertIsNone(image)
                        else:
                            with self.assertRaises(generator.GenerationError) as caught:
                                generator._convert(raw, "audio/webm", time.monotonic() + 20)
                            self.assertEqual(caught.exception.code, "media_limit")

    def test_service_media_aliases_use_fixed_supported_demuxers(self):
        cases = [("audio/mpeg", b"ID3test", "mp3"), ("audio/ogg", b"OggStest", "ogg"),
                 ("video/quicktime", b"\x00\x00\x00\x08ftyp", "mov")]
        for mime, raw, demuxer in cases:
            calls = []
            def process(argv, deadline):
                calls.append(argv)
                if "-show_entries" in argv:
                    return b'{"format":{"duration":"0.1"},"streams":[{"codec_type":"audio"}]}'
                Path(argv[-1]).write_bytes(audio())
                return b""
            with self.subTest(mime=mime), patch.object(generator, "_media_tool", return_value="/trusted/tool"), patch.object(generator, "_process", side_effect=process):
                self.assertTrue(generator._magic_matches(raw, mime))
                self.assertEqual(generator._convert(raw, mime, time.monotonic() + 30)[0], audio())
                self.assertTrue(all(call[call.index("-f") + 1] == demuxer for call in calls))
        self.assertEqual(generator._convert(audio(), "audio/x-wav", time.monotonic() + 30), (audio(), None))

    def test_default_cli_never_loads_credentials_or_makes_calls(self):
        with patch.object(generator, "ProviderClient") as client, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(generator.main([]), 0)
        client.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())["result"], "live_not_requested")

    def test_success_cli_saves_only_redacted_result_and_exact_generated_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(generator, "ROOT", Path(temporary)), patch.object(generator, "generate_app", return_value=RAW), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(generator.main(["--live"]), 0)
            artifact = Path(temporary) / "artifacts/generated-app.json"
            report = json.loads((Path(temporary) / "artifacts/generation-last-result.json").read_text())
            self.assertEqual(artifact.read_bytes(), RAW)
            self.assertEqual(report, json.loads(output.getvalue()))
            self.assertEqual(set(report), {"result", "sha256", "size_bytes", "artifact", "device_installed", "observed_at_utc"})
            self.assertFalse(report["device_installed"])


class ProviderTests(unittest.TestCase):
    def test_complete_transcript_and_late_error_discards_partial_text(self):
        self.assertEqual(providers.parse_transcript(b'{"type":"text","text":"Create"}\n{"type":"text","text":"a game"}\n'), "Create a game")
        for raw in [b'{"type":"text","text":"private"}\n{"type":"error","message":"secret"}', b'not JSON', b'{"type":"text","text":3}', b'\xff']:
            with self.assertRaises(providers.ProviderError) as caught:
                providers.parse_transcript(raw)
            self.assertEqual(caught.exception.code, "speech")
            self.assertNotIn("secret", str(caught.exception))

    def test_http_error_and_routes_never_echo_credentials_or_raw_body(self):
        error = providers._http_error("gemini", 401, b'{"error":{"message":"PRIVATE_KEY_AND_MESSAGE"}}')
        self.assertEqual(error.code, "provider_auth")
        self.assertNotIn("PRIVATE", str(error))
        for path in ["https://other.test/", "/v1beta/environments/e/files/../../.env?alt=media", "/v1beta/interactions/i?redirect=other"]:
            with patch.object(providers, "network_preflight") as preflight, self.assertRaises(providers.ProviderError):
                providers.request("gemini", "PRIVATE", path, b"", "application/json", time.monotonic() + 1, method="GET")
            preflight.assert_not_called()

    def test_total_request_deadline_interrupts_blocked_headers(self):
        released = threading.Event()
        connection = Mock()
        connection.sock.shutdown.side_effect = lambda *args: released.set()
        def blocked():
            released.wait(2)
            raise OSError("PRIVATE_RESPONSE")
        connection.getresponse.side_effect = blocked
        start = time.monotonic()
        with patch.object(providers, "network_preflight", return_value=(connection, {})), self.assertRaises(providers.ProviderError) as caught:
            providers.request("gemini", "PRIVATE", "/v1beta/interactions", b"{}", "application/json", start + 0.08)
        self.assertLess(time.monotonic() - start, 0.5)
        self.assertEqual(caught.exception.code, "deadline")
        connection.sock.shutdown.assert_called_once()
        connection.request.assert_called_once()

    def test_truncated_http_body_is_not_accepted_as_complete_speech(self):
        connection, response = Mock(), Mock()
        response.read1.side_effect = [b'{"type":"text","text":"partial"}', b'']
        response.length = 12
        response.status = 200
        connection.getresponse.return_value = response
        with patch.object(providers, "network_preflight", return_value=(connection, {})), self.assertRaises(providers.ProviderError) as caught:
            providers.request("gradium", "PRIVATE", "/api/post/speech/asr?json_config=%7B%22language%22%3A%22en%22%7D", b"wav", "audio/wav", time.monotonic() + 1)
        self.assertEqual(caught.exception.code, "provider_transport")

    def test_oversized_provider_response_has_a_fixed_diagnostic_reason(self):
        connection, response = Mock(), Mock()
        response.read1.return_value = b"PRIVATE_OVERSIZED_BODY"
        response.status = 200
        connection.getresponse.return_value = response
        with patch.object(providers, "network_preflight", return_value=(connection, {})), self.assertRaises(providers.ProviderError) as caught:
            providers.request("gemini", "PRIVATE", "/v1beta/interactions", b"{}", "application/json", time.monotonic() + 1, max_response=4)
        self.assertEqual(caught.exception.diagnostics, {"reason": "response_too_large"})
        self.assertNotIn("PRIVATE", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
