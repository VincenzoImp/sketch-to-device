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
NORMALIZED_PHOTO = b"\xff\xd8\xffsynthetic-normalized-jpeg"


def audio(seconds=0.1):
    output = io.BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(24000)
        target.writeframes(b"\x00\x00" * int(seconds * 24000))
    return output.getvalue()


def completed(raw=RAW, index=1, trace=True, marker="VALIDATED_APP"):
    result = {"id": "interaction_" + str(index), "status": "completed", "agent": generator.AGENT,
              "environment_id": "environment_1", "steps": []}
    if trace:
        result["steps"] = [
            {"type": "code_execution_call", "id": "call_1", "arguments":
             {"language": "python", "code": "subprocess.run(['python3', '/workspace/trusted_check.py'])"}},
            {"type": "code_execution_result", "call_id": "call_1", "is_error": False,
             "result": marker + " " + hashlib.sha256(raw).hexdigest() + "\n"}]
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
    def setUp(self):
        self.real_record_timing = generator._record_timing
        self.timing_patch = patch.object(generator, "_record_timing")
        self.timing_record = self.timing_patch.start()
        self.addCleanup(self.timing_patch.stop)

    def generate(self, client, prompt="Create a ten-second tap game", media=None, **profile):
        progress = []
        with patch.object(generator, "ProviderClient", return_value=client), patch.object(generator, "_record_terminal"), \
                patch.object(generator, "normalize_photo", return_value=NORMALIZED_PHOTO):
            result = generator.generate_app(prompt, media or [], lambda stage, detail: progress.append((stage, detail)), **profile)
        return result, progress

    def test_completed_requires_download_exact_hash_and_trusted_behavior(self):
        client = FakeClient()
        result, progress = self.generate(client)
        self.assertEqual(result, RAW)
        self.assertEqual(progress[-1][0], "ready")
        payload = client.payloads[0]
        self.assertEqual(payload["agent"], generator.AGENT)
        self.assertEqual(payload["agent_config"], {"type": "antigravity", "model": "gemini-3.5-flash-lite", "max_total_tokens": 200000})
        self.assertEqual(payload["environment"]["network"], "disabled")
        self.assertEqual(payload["tools"], [{"type": "code_execution"},
                                            {"type": "google_search"}, {"type": "url_context"}])
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

    def test_explicit_profiles_remain_fixed_across_payload_mount_timing_and_repair(self):
        invalid = json.loads(RAW)
        invalid["version"] = 2
        invalid = json.dumps(invalid).encode()
        for model in providers.MANAGED_MODELS:
            for budget in providers.MANAGED_TOKEN_BUDGETS:
                with self.subTest(model=model, budget=budget):
                    client = FakeClient([completed(invalid), completed(index=2)], [invalid, RAW])
                    report = {}
                    raw, _ = self.generate(client, model=model, token_budget=budget, job_seconds=180, report=report)
                    self.assertEqual(raw, RAW)
                    self.assertEqual(len(client.payloads), 2)
                    for payload in client.payloads:
                        self.assertEqual(payload["agent_config"], {"type": "antigravity", "model": model,
                                                                 "max_total_tokens": budget})
                    manifest = next(source["content"] for source in client.payloads[0]["environment"]["sources"]
                                    if source["target"].endswith("/manifest.json"))
                    self.assertEqual(json.loads(manifest)["generation_profile"], {"model": model, "token_budget": budget, "job_seconds": 180})
                    self.assertEqual(report["profile"], {"model": model, "token_budget": budget, "job_seconds": 180})
                    self.assertEqual(report["timing"]["diagnostics"]["managed_model"], model)
                    self.assertEqual(report["timing"]["diagnostics"]["token_budget"], budget)
                    self.assertEqual(report["timing"]["diagnostics"]["attempt"], 2)
                    self.assertEqual(report["timing"]["compile_ms"], 0)
                    self.assertEqual(self.timing_record.call_args.args[0]["profile"], report["profile"])
                    self.assertEqual(self.timing_record.call_args.args[0]["job_timeout_seconds"], 180)

    def test_invalid_profiles_fail_before_credentials_or_job_creation(self):
        for profile in ({"model": "PRIVATE"}, {"model": None}, {"token_budget": True},
                        {"token_budget": "100000"}, {"token_budget": 32768}, {"token_budget": 200001},
                        {"job_seconds": True}, {"job_seconds": "600"}, {"job_seconds": 601}):
            with self.subTest(profile=profile), patch.object(generator, "ProviderClient") as client, \
                    self.assertRaises(generator.GenerationError) as caught:
                generator.generate_app("public", [], lambda *args: None, **profile)
            client.assert_not_called()
            self.assertEqual(caught.exception.diagnostics, {"reason": "invalid_generation_profile"})
            self.assertNotIn("PRIVATE", str(caught.exception))
        self.timing_record.assert_not_called()
        for args in (["--live", "--model", "PRIVATE"], ["--live", "--token-budget", "PRIVATE"],
                     ["--live", "--job-seconds", "PRIVATE"]):
            with patch.object(generator, "ProviderClient") as client, contextlib.redirect_stderr(io.StringIO()) as error, \
                    self.assertRaises(SystemExit) as caught:
                generator.main(args)
            self.assertEqual(caught.exception.code, 2)
            self.assertNotIn("PRIVATE", error.getvalue())
            client.assert_not_called()

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
            self.assertEqual(caught.exception.code, "generation_stalled")
            self.assertEqual(caught.exception.diagnostics["reason"], "validation_stalled")
            self.assertEqual(len(client.payloads), 2)

    def test_real_runtime_rejects_wrong_score_despite_successful_remote_marker(self):
        app = json.loads(RAW)
        tap = next(widget for screen in app["screens"] for widget in screen["widgets"] if widget["id"] == "tap")
        tap["on_press"][0]["amount"] = 2
        raw = json.dumps(app).encode()
        client = FakeClient([completed(raw)] * 3, [raw] * 3)
        with self.assertRaises(generator.GenerationError) as caught:
            self.generate(client)
        self.assertEqual(caught.exception.code, "generation_stalled")

    def test_changed_invalid_artifacts_can_repair_four_times_without_round_ceiling(self):
        artifacts = []
        for version in (2, 3, 4, 5):
            app = json.loads(RAW)
            app["version"] = version
            artifacts.append(json.dumps(app).encode())
        artifacts.append(RAW)
        client = FakeClient([completed(raw, index=index + 1) for index, raw in enumerate(artifacts)], artifacts)
        report = {}
        raw, progress = self.generate(client, report=report)
        self.assertEqual(raw, RAW)
        self.assertEqual(len(client.payloads), 5)
        self.assertEqual([stage for stage, _ in progress].count("repairing"), 4)
        self.assertEqual(report["timing"]["diagnostics"]["repair_count"], 4)
        self.assertEqual(report["timing"]["diagnostics"]["attempt"], 5)
        self.assertEqual(report["profile"]["job_seconds"], 600)
        for index in range(1, 5):
            self.assertEqual(client.payloads[index]["previous_interaction_id"], "interaction_" + str(index))

    def test_repeated_artifact_failure_stalls_even_after_a_different_invalid_artifact(self):
        a = json.loads(RAW); a["version"] = 2
        b = json.loads(RAW); b["version"] = 3
        artifacts = [json.dumps(a).encode(), json.dumps(b).encode(), json.dumps(a).encode()]
        client = FakeClient([completed(raw, index=index + 1) for index, raw in enumerate(artifacts)], artifacts)
        with self.assertRaises(generator.GenerationError) as caught:
            self.generate(client)
        self.assertEqual(caught.exception.code, "generation_stalled")
        self.assertEqual(caught.exception.diagnostics["stalled_failure_count"], 2)
        self.assertEqual(caught.exception.diagnostics["attempt"], 3)
        self.assertEqual(len(client.payloads), 3)

    def test_original_job_deadline_stops_polling_and_reserves_cancellation_time(self):
        for seconds in (180, 600):
            now = [100.0]
            response = {"id": "interaction_1", "status": "in_progress"}
            client = FakeClient([response])
            original = client.google
            deadlines = []
            def google(method, path, **kwargs):
                deadlines.append(client.deadline)
                if path.endswith("/cancel"):
                    return original(method, path, **kwargs)
                now[0] = 100.0 + seconds - 10
                return response
            client.google = google
            with self.subTest(seconds=seconds), patch.object(generator.time, "monotonic", side_effect=lambda: now[0]), \
                    patch.object(generator.time, "sleep"), self.assertRaises(generator.GenerationError) as caught:
                self.generate(client, job_seconds=seconds)
            self.assertEqual(caught.exception.code, "deadline")
            self.assertEqual(deadlines, [100 + seconds - 10, 100 + seconds])
            self.assertEqual(caught.exception.diagnostics["cancellation"], "confirmed")
            self.assertEqual(caught.exception.diagnostics["elapsed_ms"], (seconds - 10) * 1000)
            self.assertEqual(len(client.payloads), 1)

    def test_search_steps_never_replace_paired_checker_execution(self):
        response = completed()
        marker = "VALIDATED_APP " + hashlib.sha256(RAW).hexdigest()
        research = [
            {"type": "google_search_call", "id": "search_1", "arguments": {"query": "public reference"}},
            {"type": "google_search_result", "call_id": "search_1", "result": marker},
            {"type": "url_context_call", "id": "url_1", "arguments": {"urls": ["https://example.com"]}},
            {"type": "url_context_result", "call_id": "url_1", "result": marker},
        ]
        response["steps"] = research[:2] + response["steps"][:1] + research[2:] + response["steps"][1:]
        client = FakeClient([response])
        self.assertEqual(self.generate(client)[0], RAW)
        manifest = next(source for source in client.payloads[0]["environment"]["sources"]
                        if source["target"] == "/workspace/agent-sdk/manifest.json")
        self.assertEqual(json.loads(manifest["content"])["managed_tools"],
                         [tool["type"] for tool in client.payloads[0]["tools"]])
        self.assertEqual(generator._execution_hashes({"steps": research}), set())
        forged = research + [{"type": "code_execution_result", "call_id": "search_1", "result": marker}]
        self.assertEqual(generator._execution_hashes({"steps": forged}), set())

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
        self.assertEqual(diagnostic["token_budget"], 200000)
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
                    "usage": {"total_tokens": 382949, "total_cached_tokens": 332474}, "steps": []}
        # Reproduce the observed SDK run against its explicit historical cap.
        with self.assertRaises(generator.GenerationError) as caught:
            self.generate(FakeClient([response]), token_budget=50000)
        self.assertEqual(caught.exception.diagnostics["effective_tokens"], 50475)
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
            unsupported = json.dumps({"kind": "unsupported_request", "features": ["camera_capture"]})
            refused = subprocess.run(["/bin/bash", "-c", command.replace("REPLACE_WITH_REQUEST_SPECIFIC_JSON", unsupported)],
                                     cwd=workspace, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
            self.assertEqual(refused.returncode, 0)
            self.assertEqual(refused.stdout.decode().strip(), "UNSUPPORTED_REQUEST " + hashlib.sha256((unsupported + "\n").encode()).hexdigest())

    def test_sdk_exact_mount_mapping_hash_manifest_and_executable_examples(self):
        sources=generator._sources({"tap_game":False,"duration_seconds":None})
        mapping={source["target"]:source["content"] for source in sources}
        self.assertEqual(len(mapping),len(sources))
        self.assertEqual(mapping[".agents/AGENTS.md"],(ROOT/"agent-sdk/.agents/AGENTS.md").read_text())
        self.assertEqual(mapping[".agents/skills/device-app-development/SKILL.md"],
                         (ROOT/"agent-sdk/.agents/skills/device-app-development/SKILL.md").read_text())
        self.assertNotIn((ROOT/"AGENTS.md").read_text(),mapping.values())
        manifest=json.loads(mapping["/workspace/agent-sdk/manifest.json"])
        capabilities=json.loads(mapping["/workspace/contracts/runtime-capabilities.json"])
        self.assertEqual(manifest["source_runtime_version"],capabilities["runtime_version"])
        self.assertEqual(manifest["source_schema_versions"],capabilities["schema_versions"])
        self.assertIsNone(manifest["device_runtime"]["version"])
        self.assertEqual(manifest["device_runtime"]["status"],"not_attested_by_generator")
        self.assertEqual(manifest["managed_tools"],list(generator.MANAGED_TOOLS))
        self.assertEqual(len(manifest["files"]),len(sources)-1)
        for item in manifest["files"]:
            data=mapping[item["target"]].encode()
            self.assertEqual(item["sha256"],hashlib.sha256(data).hexdigest())
            self.assertEqual(item["size_bytes"],len(data))
        with tempfile.TemporaryDirectory() as temporary:
            workspace=Path(temporary)
            for source in sources:
                target=workspace/source["target"].removeprefix("/workspace/")
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_text(source["content"])
            command=[sys.executable,"-B",str(workspace/"agent-sdk/run_examples.py")]
            passed=subprocess.run(command,cwd=workspace,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
            self.assertEqual(passed.returncode,0,passed.stderr.decode())
            reports=[json.loads(line) for line in passed.stdout.splitlines()]
            self.assertEqual({report["example"] for report in reports},{"counter","settings","timer","colors"})
            self.assertEqual(sum(report["checkpoints"] for report in reports),18)
            target=workspace/"agent-sdk/examples/counter.json"
            broken=json.loads(target.read_text());broken["screens"][0]["widgets"][1]["on_press"][0]["amount"]=2
            target.write_text(json.dumps(broken))
            failed=subprocess.run(command+["counter"],cwd=workspace,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
            self.assertNotEqual(failed.returncode,0)
            self.assertNotIn(b'"evidence"',failed.stdout)

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

    def test_research_trace_retains_documented_steps_and_counts_without_thoughts(self):
        response = completed()
        research = [
            {"type": "google_search_call", "id": "s", "arguments": {"queries": ["public colors"]}},
            {"type": "google_search_result", "call_id": "s", "is_error": False, "result": [{"title": "Public"}]},
            {"type": "url_context_call", "id": "u", "arguments": {"urls": ["https://example.com"]}},
            {"type": "url_context_result", "call_id": "u", "is_error": True,
             "result": [{"url": "https://example.com", "status": "error"}]},
            {"type": "PRIVATE_UNKNOWN_TYPE", "text": "PRIVATE_UNKNOWN_BODY"},
            {"type": "model_thought", "text": "PRIVATE_THOUGHT"},
        ]
        response["steps"] += research
        with tempfile.TemporaryDirectory() as temporary, patch.object(generator, "ROOT", Path(temporary)):
            profile = {"model": "gemini-3.5-flash-lite", "token_budget": 100000, "job_seconds": 600}
            self.assertTrue(generator._record_terminal(response, [], {}, 1, profile))
            path = Path(temporary) / "private/provider/managed-last-execution.json"
            record = json.loads(path.read_bytes())
            self.assertEqual(record["profile"], profile)
            self.assertEqual(record["token_budget"], 100000)
            self.assertEqual(record["steps"][2:], research[:4])
            self.assertEqual(record["diagnostics"]["step_counts"]["other"], 2)
            for name in providers.RESEARCH_STEP_TYPES:
                self.assertEqual(record["diagnostics"]["step_counts"][name], 1)
            self.assertNotIn("PRIVATE", path.read_text())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_per_call_run_id_correlates_terminal_and_timing_despite_last_file_overwrite(self):
        sources = generator._sources({"tap_game": True, "duration_seconds": 10})
        reports = []
        with tempfile.TemporaryDirectory() as temporary, patch.object(generator, "ROOT", Path(temporary)), \
                patch.object(generator, "_sources", return_value=sources), \
                patch.object(generator, "_record_timing", side_effect=self.real_record_timing):
            for status in ("completed", "incomplete"):
                response = completed(); response["status"] = status
                report = {}
                with patch.object(generator, "ProviderClient", return_value=FakeClient([response])):
                    self.assertEqual(generator.generate_app("ten-second tap game", [], lambda *args: None, report=report), RAW)
                directory = Path(temporary) / "private/provider"
                trace = json.loads((directory / "managed-last-execution.json").read_bytes())
                timing = json.loads((directory / "managed-last-timing.json").read_bytes())
                run_id = report["timing"]["run_id"]
                self.assertRegex(run_id, r"^[a-f0-9]{32}$")
                self.assertEqual(trace["run_id"], run_id)
                self.assertEqual(timing["run_id"], run_id)
                self.assertEqual(trace["diagnostics"]["interaction_status"], status)
                reports.append(report)
            self.assertNotEqual(reports[0]["timing"]["run_id"], reports[1]["timing"]["run_id"])
            self.assertNotEqual(trace["run_id"], reports[0]["timing"]["run_id"])
            response["steps"][1]["result"] = "x" * (generator.MAX_TERMINAL_TRACE + 1)
            self.assertTrue(generator._record_terminal(response, [], {}, 1, run_id=reports[-1]["timing"]["run_id"]))
            trimmed = json.loads((directory / "managed-last-execution.json").read_bytes())
            self.assertEqual(trimmed["run_id"], reports[-1]["timing"]["run_id"])
            self.assertEqual(trimmed["trace_omitted"], "size_limit")
            self.assertFalse(generator._record_terminal(response, [], {}, 1, run_id="PRIVATE"))
            self.assertEqual(json.loads((directory / "managed-last-execution.json").read_bytes()), trimmed)

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
        self.assertEqual(caught.exception.diagnostics["poll_count"], 1)
        self.assertEqual(caught.exception.diagnostics["cancellation"], "confirmed")

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
            self.assertEqual(base64.b64decode(content[1]["data"]), NORMALIZED_PHOTO)
            self.assertEqual(content[1]["mime_type"], "image/jpeg")

    def test_freezes_media_before_client_and_rejects_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "image.png"
            original = b"\x89PNG\r\n\x1a\noriginal"
            source.write_bytes(original)
            client = FakeClient()
            def factory(deadline):
                source.write_bytes(b"changed")
                return client
            with patch.object(generator, "ProviderClient", side_effect=factory), patch.object(generator, "_record_terminal"), \
                    patch.object(generator, "normalize_photo", return_value=NORMALIZED_PHOTO) as normalize:
                generator.generate_app("ten-second tap game", [{"path": source, "mime_type": "image/png"}], lambda *args: None)
            self.assertEqual(normalize.call_args.args[:2], (original, "image/png"))
            self.assertEqual(base64.b64decode(client.payloads[0]["input"][1]["data"]), NORMALIZED_PHOTO)
            link = Path(temporary) / "link.png"
            link.symlink_to(source)
            with self.assertRaises(generator.GenerationError):
                generator._snapshot("request", [{"path": link, "mime_type": "image/png"}])

    def test_duration_enforcement_and_non_game_runtime_checks(self):
        self.assertEqual(generator.requirements_for("a five-minute focus timer")["duration_seconds"], 300)
        for request in ("A scoreboard counter: tap to add one point; no timer.", "Create a tap game."):
            self.assertEqual(generator.requirements_for(request), {"tap_game": False, "duration_seconds": None})
        self.assertEqual(generator.requirements_for("Create a fifteen-second tap game."),
                         {"tap_game": True, "duration_seconds": 15})
        with self.assertRaises(ValueError):
            generator.verify_behavior(RAW, {"tap_game": True, "duration_seconds": 15})
        raw = (ROOT / "contracts/fixtures/focus-timer.json").read_bytes()
        report = generator.verify_behavior(raw, {"tap_game": False, "duration_seconds": None})
        self.assertGreater(report["checks"], 1)
        self.assertEqual(report["coverage"], "bounded_runtime_controls_and_timers")

    def test_explicit_titles_are_checked_without_greedy_speech_rewriting(self):
        for phrase in ('Create an app called "Hello World" with one button.',
                       'Create an app named "Hello World". It has a button.',
                       'The app title is "Hello World".'):
            self.assertEqual(generator.requirements_for(phrase)["title"], "Hello World")
        for phrase in ('A button labeled "Hello World".', 'Create an app named Hello World with one button.',
                       'Create an app called Hello World on my display.', 'Create a counter named Hello World.',
                       'Create an app with a button called "Go".', 'Add a toggle named "Sound".'):
            self.assertNotIn("title", generator.requirements_for(phrase))
        with self.assertRaises(ValueError):
            generator.verify_behavior(RAW, generator.requirements_for('An app called "Hello World".'))
        renamed = json.loads(RAW)
        renamed["name"] = "Hello World"
        self.assertGreater(generator.verify_behavior(json.dumps(renamed).encode(),
                           generator.requirements_for('An app called "Hello World".'))["checks"], 0)

    def test_phase_timings_use_monotonic_observation_and_zero_app_compilation(self):
        now=[100.0]
        timing=generator._PhaseTiming(clock=lambda:now[0])
        initial=self.timing_record.call_args.args[0]
        self.assertEqual(initial["status"],"in_progress")
        self.assertNotIn("finished_at_utc",initial)
        now[0]=108;timing.mark("managed_generation")
        now[0]=168;timing.mark("artifact_download")
        now[0]=169;timing.mark("host_checks")
        now[0]=169.25;timing.mark("cleanup")
        now[0]=169.5;timing.finish("completed",source=RAW)
        report=self.timing_record.call_args.args[0]
        self.assertEqual(report["phase_ms"],{"input_preparation":8000,"managed_generation":60000,
            "artifact_download":1000,"host_checks":250,"cleanup":250})
        self.assertEqual(report["total_ms"],69500)
        self.assertEqual(report["compile_ms"],0)
        self.assertEqual(report["source_sha256"],hashlib.sha256(RAW).hexdigest())
        self.assertEqual(report["run_id"],initial["run_id"])
        self.assertEqual(report["profile"], {"model": "gemini-3.5-flash-lite", "token_budget": 200000, "job_seconds": 600})
        self.assertEqual(timing.summary()["total_ms"], 69500)
        with tempfile.TemporaryDirectory() as temporary,patch.object(generator,"ROOT",Path(temporary)):
            self.real_record_timing(report)
            path=Path(temporary)/"private/provider/managed-last-timing.json"
            self.assertEqual(json.loads(path.read_text()),report)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)

    def test_failed_run_replaces_started_timing_without_claiming_provider_success(self):
        client=FakeClient([{"id":"interaction_1","status":"failed"}])
        with self.assertRaises(generator.GenerationError):self.generate(client)
        started,finished=[call.args[0] for call in self.timing_record.call_args_list]
        self.assertEqual(started["run_id"],finished["run_id"])
        self.assertEqual(finished["status"],"failed")
        self.assertNotIn("source_sha256",finished)
        self.assertEqual(finished["compile_ms"],0)

    def test_diverse_compositions_and_static_apps_use_actual_reference_runtime(self):
        from runtime.reference import ReferenceRuntime
        def app(screens, state=None):
            value = json.loads(RAW)
            value.update(name="Example", state=state or {}, screens=screens, initial_screen=screens[0]["id"])
            return json.dumps(value).encode()
        counter = app([{"id":"home", "title":"Counter", "widgets":[
            {"id":"value", "type":"counter", "state_key":"count"},
            {"id":"plus", "type":"button", "text":"Add", "on_press":[{"type":"increment","state_key":"count","amount":1}]},
            {"id":"reset", "type":"button", "text":"Reset", "on_press":[{"type":"set","state_key":"count","value":0}]}]}], {"count":0})
        toggle = app([{"id":"home", "title":"Switch", "widgets":[
            {"id":"switch", "type":"toggle", "text":"Enabled", "state_key":"enabled"}]}], {"enabled":False})
        colors = ["#FF69B4", "#164EAD", "#008000"]
        navigation = app([{"id":"screen_"+str(index), "title":"Hello World", "widgets":[
            {"id":"button_"+str(index), "type":"button", "text":"Change color", "background_color":color,
             "on_press":[{"type":"navigate", "screen_id":"screen_"+str((index+1)%3)}]}]}
            for index,color in enumerate(colors)])
        timer = (ROOT / "contracts/fixtures/focus-timer.json").read_bytes()
        for raw in (counter,toggle,navigation,timer):
            self.assertGreater(generator.verify_behavior(raw, {})["checks"],0)
        runtime=ReferenceRuntime(counter)
        runtime.press("reset",0,runtime.event_token())  # A stable reset is legitimate when another control works.
        runtime.press("plus",1,runtime.event_token())
        runtime.press("plus",2,runtime.event_token())
        self.assertEqual(runtime.state["count"],2)
        runtime.press("reset",3,runtime.event_token())
        self.assertEqual(runtime.state["count"],0)
        runtime=ReferenceRuntime(toggle)
        runtime.press("switch",1,runtime.event_token());self.assertTrue(runtime.state["enabled"])
        runtime.press("switch",2,runtime.event_token());self.assertFalse(runtime.state["enabled"])
        runtime=ReferenceRuntime(navigation)
        for index in range(7):
            screen=next(screen for screen in runtime.app["screens"] if screen["id"]==runtime.screen)
            self.assertEqual(screen["widgets"][0]["background_color"],colors[index%3])
            runtime.press(screen["widgets"][0]["id"],index,runtime.event_token())
        noop=app([{"id":"home","title":"No effect","widgets":[
            {"id":"button","type":"button","text":"Does nothing","on_press":[]}]}])
        self.assertEqual(generator.verify_behavior(noop,{})["checks"],1)
        static=app([{"id":"home","title":"Status","widgets":[{"id":"status","type":"label","text":"Ready"}]}])
        self.assertEqual(generator.verify_behavior(static,{}),{"checks":0,"coverage":"validated_structure_no_control_events"})
        hidden=app([{"id":"home","title":"Bookkeeping","widgets":[
            {"id":"press","type":"button","text":"Press","on_press":[{"type":"increment","state_key":"hidden","amount":1}]}]}],{"hidden":0})
        self.assertGreater(generator.verify_behavior(hidden,{})["checks"],0)  # Execution validity is not visual/intent fidelity.

    def test_unsupported_result_requires_exact_typed_bytes_and_paired_marker(self):
        raw=json.dumps({"kind":"unsupported_request","features":["camera_capture"]}).encode()
        for state in ("completed","incomplete"):
            response=completed(raw,marker="UNSUPPORTED_REQUEST");response["status"]=state
            client=FakeClient([response],[raw]);progress=[]
            with patch.object(generator,"ProviderClient",return_value=client), patch.object(generator,"_record_terminal"), self.assertRaises(generator.GenerationError) as caught:
                generator.generate_app("Use the device camera",[],lambda stage,detail:progress.append(stage))
            self.assertEqual(caught.exception.code,"unsupported_request")
            self.assertEqual(caught.exception.diagnostics["unsupported_features"],["camera_capture"])
            self.assertNotIn("ready",progress)
            self.assertEqual(len(client.payloads),1)
            self.assertEqual(caught.exception.diagnostics["interaction_status"],state)
        for kind in ("wrong_marker","wrong_hash","unpaired"):
            response=completed(raw,marker="UNSUPPORTED_REQUEST")
            if kind=="wrong_marker":response["steps"][1]["result"]="VALIDATED_APP "+hashlib.sha256(raw).hexdigest()
            elif kind=="wrong_hash":response["steps"][1]["result"]="UNSUPPORTED_REQUEST "+"0"*64
            else:response["steps"][1]["call_id"]="other"
            client=FakeClient([response]*3,[raw]*3)
            with self.subTest(kind=kind),self.assertRaises(generator.GenerationError) as caught:self.generate(client,"Use the device camera")
            self.assertEqual(caught.exception.code,"generation_stalled")
        for features in ([],["PRIVATE"],["camera_capture"]*2,[{}]):
            with self.assertRaises(ValueError):generator.unsupported_features(json.dumps({"kind":"unsupported_request","features":features}).encode())

    def test_unsupported_camera_service_failure_preserves_actual_prior_active_record(self):
        from backend.server import Application
        from tests.test_deployments import acknowledgment
        refusal=json.dumps({"kind":"unsupported_request","features":["camera_capture"]}).encode()
        client=FakeClient([completed(refusal,marker="UNSUPPORTED_REQUEST")],[refusal])
        with tempfile.TemporaryDirectory() as temporary:
            app=Application(Path(temporary),generator=generator.generate_app)
            with app.store() as store:
                intent=store.accept_intent(app.config["session_id"],app.config["device_id"],"previous",b"fixture")
                previous=store.publish(app.config["session_id"],intent["intent_id"],RAW)
                store.record_ack(app.config["device_id"],acknowledgment(previous,device=app.config["device_id"]))
            with patch.object(generator,"ProviderClient",return_value=client),patch.object(generator,"_record_terminal"):
                job=app.generate({"request_id":"c"*32,"prompt":"Use the device camera","uploads":[]})["job_id"]
                end=time.monotonic()+3
                while app.busy and time.monotonic()<end:time.sleep(.005)
                self.assertFalse(app.busy)
            self.assertEqual(app.status(job)["stage"],"failed")
            self.assertEqual(app.status(job)["detail"],"unsupported_request")
            with app.store() as store:
                self.assertEqual(store.active_for_session(app.config["session_id"],app.config["device_id"]),previous)
                self.assertIsNone(store.desired_for_device(app.config["device_id"]))
                self.assertEqual(store._db.execute("SELECT COUNT(*) FROM deployments").fetchone()[0],1)

    def test_cancellation_mismatch_and_failure_are_honest_without_retries(self):
        for result,expected in (({"id":"wrong","status":"cancelled"},"unconfirmed"),(OSError("PRIVATE"),"failed")):
            client=FakeClient([{"id":"interaction_1","status":"in_progress"}]);calls=[]
            def request(method,path,**kwargs):
                calls.append((method,path))
                if not path.endswith("/cancel"):raise providers.ProviderError("provider_request",{"http_status":503,"http_category":"provider_http_error"})
                if isinstance(result,Exception):raise result
                return result
            client.google=request
            with patch.object(generator.time,"sleep"),self.assertRaises(generator.GenerationError) as caught:self.generate(client)
            self.assertEqual(caught.exception.diagnostics["cancellation"],expected)
            self.assertEqual(caught.exception.diagnostics["http_status"],503)
            self.assertEqual(len(calls),2)
            self.assertNotIn("PRIVATE",json.dumps(caught.exception.diagnostics))

    def test_malformed_repair_job_cancels_new_id_instead_of_reusing_prior_terminal_state(self):
        client=FakeClient([completed(b'{}'),{"id":"interaction_2","status":"UNKNOWN"}],[b'{}'])
        original=client.google
        def request(method,path,**kwargs):
            if path.endswith("/cancel"):
                client.calls.append((method,path))
                return {"id":"interaction_2","status":"cancelled"}
            return original(method,path,**kwargs)
        client.google=request
        with self.assertRaises(generator.GenerationError) as caught:self.generate(client)
        self.assertEqual(caught.exception.diagnostics["reason"],"unknown_interaction_status")
        self.assertEqual(caught.exception.diagnostics["cancellation"],"confirmed")
        self.assertEqual([call for call in client.calls if call[1].endswith("/cancel")],
                         [("POST","/v1beta/interactions/interaction_2/cancel")])
        self.assertEqual(client.payloads[1]["previous_interaction_id"],"interaction_1")

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
        self.assertEqual(calls[-1][calls[-1].index("-t") + 1], "61")

    def test_overlong_recording_rejected_before_transcription(self):
        with self.assertRaises(providers.ProviderError) as caught:
            providers.wav_duration(audio(60.001))
        self.assertEqual(caught.exception.code, "media_limit")
        metadata = b'{"format":{"duration":"60.001"},"streams":[{"codec_type":"audio"}]}'
        measured = b'out_time_us=60001000\nprogress=end\n'
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
            for mime, seconds, limit in (("audio/webm", 60, 60), ("audio/webm", 60.001, 60),
                                         ("audio/webm", 61, 60), ("video/webm", 30, 30),
                                         ("video/webm", 30.001, 30)):
                for seekable in (True, False):
                    with self.subTest(mime=mime, seconds=seconds, seekable=seekable):
                        argv = [ffmpeg, "-nostdin", "-v", "error", "-y", "-f", "lavfi",
                                "-i", "sine=frequency=440:sample_rate=48000", "-t", str(seconds),
                                "-c:a", "libopus", "-f", "webm", str(target) if seekable else "pipe:1"]
                        encoded = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                                 stderr=subprocess.PIPE, check=True, timeout=20)
                        raw = target.read_bytes() if seekable else encoded.stdout
                        if seconds == limit:
                            wav, image = generator._convert(raw, mime, time.monotonic() + 20)
                            self.assertEqual(providers.wav_duration(wav), limit)
                            self.assertIsNone(image)
                        else:
                            with self.assertRaises(generator.GenerationError) as caught:
                                generator._convert(raw, mime, time.monotonic() + 20)
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
            self.assertEqual(set(report), {"result", "sha256", "size_bytes", "artifact", "device_installed", "observed_at_utc", "profile"})
            self.assertFalse(report["device_installed"])

    def test_cli_profile_and_phase_report_belong_to_this_call_on_success_and_failure(self):
        sources = generator._sources({"tap_game": True, "duration_seconds": 10})
        for fails in (False, True):
            response = {"id": "interaction_1", "status": "failed"} if fails else completed()
            client = FakeClient([response])
            with self.subTest(fails=fails), tempfile.TemporaryDirectory() as temporary, \
                    patch.object(generator, "ROOT", Path(temporary)), patch.object(generator, "_sources", return_value=sources), \
                    patch.object(generator, "ProviderClient", return_value=client), patch.object(generator, "_record_terminal"), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(generator.main(["--live", "--model", "gemini-3.5-flash-lite", "--token-budget", "100000", "--job-seconds", "180"]), int(fails))
                report = json.loads(output.getvalue().splitlines()[-1])
                self.assertEqual(report["profile"], {"model": "gemini-3.5-flash-lite", "token_budget": 100000, "job_seconds": 180})
                self.assertEqual(report["timing"]["status"], "failed" if fails else "completed")
                self.assertEqual(set(report["timing"]["phase_ms"]), generator.TIMING_PHASES)
                self.assertEqual(report["timing"]["compile_ms"], 0)
                self.assertEqual(report["timing"]["diagnostics"]["interaction_status"], "failed" if fails else "completed")
                self.assertEqual(report, json.loads((Path(temporary) / "artifacts/generation-last-result.json").read_bytes()))
                self.assertNotIn("interaction_1", json.dumps(report))
                if not fails:
                    self.assertEqual((Path(temporary) / "artifacts/generated-app.json").read_bytes(), RAW)
                else:
                    self.assertFalse((Path(temporary) / "artifacts/generated-app.json").exists())

    def test_live_cli_default_reaches_provider_mount_and_saved_report(self):
        sources = generator._sources({"tap_game": True, "duration_seconds": 10})
        client = FakeClient()
        expected = {"model": "gemini-3.5-flash-lite", "token_budget": 200000, "job_seconds": 600}
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(generator, "ROOT", Path(temporary)), patch.object(generator, "_sources", return_value=sources), \
                patch.object(generator, "ProviderClient", return_value=client), patch.object(generator, "_record_terminal"), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(generator.main(["--live"]), 0)
            payload = client.payloads[0]
            self.assertEqual(payload["agent_config"], {"type": "antigravity", "model": expected["model"], "max_total_tokens": expected["token_budget"]})
            manifest = next(source["content"] for source in payload["environment"]["sources"]
                            if source["target"].endswith("/manifest.json"))
            self.assertEqual(json.loads(manifest)["generation_profile"], expected)
            report = json.loads(output.getvalue().splitlines()[-1])
            self.assertEqual(report["profile"], expected)
            self.assertEqual(report["timing"]["diagnostics"]["managed_model"], expected["model"])
            self.assertEqual(report["timing"]["diagnostics"]["token_budget"], expected["token_budget"])
            self.assertEqual(report["timing"]["diagnostics"]["job_timeout_seconds"], expected["job_seconds"])
            self.assertEqual(report, json.loads((Path(temporary) / "artifacts/generation-last-result.json").read_bytes()))
            self.assertEqual((Path(temporary) / "artifacts/generated-app.json").read_bytes(), RAW)


class ProviderTests(unittest.TestCase):
    def test_http_status_and_categories_remain_precise_and_redacted(self):
        for status in (400,404,408,500,502,503):
            error=providers._http_error("gemini",status,b'{"error":{"message":"PRIVATE","metadata":{"key":"PRIVATE"}}}')
            self.assertEqual(error.code,"provider_request")
            self.assertEqual(error.diagnostics["http_status"],status)
            self.assertNotIn("PRIVATE",json.dumps(error.diagnostics))
        raw=b'{"error":{"status":"INVALID_ARGUMENT","details":[{"@type":"type.googleapis.com/google.rpc.ErrorInfo","domain":"googleapis.com","reason":"API_KEY_INVALID","metadata":{"secret":"PRIVATE"}}]}}'
        error=providers._http_error("gemini",400,raw)
        self.assertEqual(error.code,"provider_auth")
        self.assertEqual(error.diagnostics["google_error_reason"],"API_KEY_INVALID")
        self.assertEqual(error.diagnostics["google_error_status"],"INVALID_ARGUMENT")
        self.assertNotIn("PRIVATE",json.dumps(error.diagnostics))
        filtered=providers.safe_diagnostics({"http_status":True,"http_category":"PRIVATE",
            "cancellation":"PRIVATE","unsupported_features":["camera_capture","PRIVATE",{}],"poll_count":False})
        self.assertEqual(filtered,{"unsupported_features":["camera_capture"]})

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
