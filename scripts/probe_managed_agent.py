#!/usr/bin/env python3
"""Probe real managed execution and artifact retrieval with public fixed input.

Python 3.9+ standard library; --live is required for provider requests.
No repository files, user media, credentials or process environment enter prompts.
"""

import datetime
import hashlib
import json
import queue
import re
import socket
import sys
import threading
import time

import probe_providers as providers


AGENT = "antigravity-preview-09-2026"
HOST = providers.HOSTS["gemini"]
SOURCE_PATH = "/workspace/provider_probe.py"
ARTIFACT_NAME = "provider_probe_result.txt"
EXPECTED = b"MANAGED_AGENT_ARTIFACT_V1\n"
EXPECTED_HASH = hashlib.sha256(EXPECTED).hexdigest()
MARKER = "PROBE_EXECUTED " + EXPECTED_HASH
SOURCE = (
    "from pathlib import Path\n"
    "import hashlib\n"
    "payload = b'MANAGED_AGENT_ARTIFACT_V1\\n'\n"
    "target = Path('/workspace/provider_probe_result.txt')\n"
    "target.write_bytes(payload)\n"
    "assert target.read_bytes() == payload\n"
    "print('PROBE_EXECUTED ' + hashlib.sha256(target.read_bytes()).hexdigest())\n"
)
MAX_JSON = 262144
TOKEN_BUDGETS = (4096, 16384)
USAGE_FIELDS = ("total_input_tokens", "total_output_tokens", "total_thought_tokens",
                "total_cached_tokens", "total_tool_use_tokens", "total_tokens")
TERMINAL = {"completed", "failed", "cancelled", "incomplete"}
FAILURE_CODES = {
    "job_deadline", "request_timeout", "network_unavailable", "transport_failed",
    "response_too_large", "invalid_json_response", "unexpected_response_shape",
    "invalid_resource_id", "unknown_interaction_status", "unexpected_agent",
    "interaction_identity_changed", "interaction_not_completed", "provider_http_error",
    "artifact_not_found", "artifact_path_ambiguous", "artifact_content_mismatch",
    "execution_evidence_missing", "internal_probe_error", "invalid_route", "interrupted",
}


class ManagedFailure(Exception):
    def __init__(self, code, provider_error=None):
        super().__init__(code if code in FAILURE_CODES else "internal_probe_error")
        # Only analyze_response() may supply this already-reduced object.
        self.provider_error = provider_error


def create_payload(max_total_tokens=4096):
    return {
        "agent": AGENT,
        "input": (
            "Run the existing public script /workspace/provider_probe.py exactly once "
            "using the code_execution tool and Python 3. Do not edit it or recreate its "
            "output using filesystem tools. The script writes a small test artifact and "
            "prints an execution marker. Do not browse, install packages, inspect other "
            "files, or ask questions. Finish after the command succeeds."
        ),
        "environment": {
            "type": "remote", "network": "disabled",
            "sources": [{"type": "inline", "target": SOURCE_PATH, "content": SOURCE}],
        },
        "tools": [{"type": "code_execution"}],
        "agent_config": {"type": "antigravity", "max_total_tokens": max_total_tokens},
        "background": True,
        "store": True,
    }


def resource_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,4096}", value):
        raise ManagedFailure("invalid_resource_id")
    return value


def allowed_route(method, path):
    identifier = r"[A-Za-z0-9_-]{1,4096}"
    if method == "POST":
        return path == "/v1beta/interactions" or bool(re.fullmatch(
            r"/v1beta/interactions/" + identifier + r":cancel", path))
    if method == "GET":
        return bool(re.fullmatch(r"/v1beta/interactions/" + identifier, path) or re.fullmatch(
            r"/v1beta/environments/" + identifier + r"/files(?:\?recursive=true|/"
            r"(?:workspace/)?provider_probe_result\.txt\?alt=media)", path))
    return False


class Transport:
    """One verified direct connection per request; no retry or redirect follow."""

    def __init__(self, key, deadline):
        self.key = key
        self.deadline = deadline
        self.network = {"dns": "not_tested", "tls": "not_tested"}
        self.requests_sent = 0

    def send(self, method, path, payload=None, limit=MAX_JSON):
        if not allowed_route(method, path):
            raise ManagedFailure("invalid_route")
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise ManagedFailure("job_deadline")
        request_deadline = min(self.deadline, time.monotonic() + 30)
        outcomes, stream = queue.Queue(maxsize=1), []

        def exchange():
            connection = response = None
            try:
                connection, self.network = providers.network_preflight(
                    HOST, min(8, max(0.001, request_deadline - time.monotonic())))
                if connection is None:
                    raise ManagedFailure("network_unavailable")
                raw_socket = connection.sock
                stream.append(raw_socket)
                remaining_io = request_deadline - time.monotonic()
                if remaining_io <= 0:
                    raise ManagedFailure("request_timeout")
                raw_socket.settimeout(remaining_io)
                headers = {"x-goog-api-key": self.key, "Accept": "application/json",
                           "Connection": "close"}
                body = None
                if payload is not None:
                    headers["Content-Type"] = "application/json"
                    body = json.dumps(payload).encode("utf-8")
                self.requests_sent += 1
                connection.request(method, path, body=body, headers=headers)
                response = connection.getresponse()
                chunks, size = [], 0
                while True:
                    remaining_io = request_deadline - time.monotonic()
                    if remaining_io <= 0:
                        raise ManagedFailure("request_timeout")
                    raw_socket.settimeout(remaining_io)
                    chunk = response.read1(min(4096, limit + 1 - size))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    size += len(chunk)
                    if size > limit:
                        raise ManagedFailure("response_too_large")
                outcomes.put((True, (response.status, b"".join(chunks))))
            except Exception as exc:
                outcomes.put((False, exc))
            finally:
                if response is not None:
                    response.close()
                if connection is not None:
                    connection.close()

        threading.Thread(target=exchange, daemon=True).start()
        try:
            success, outcome = outcomes.get(timeout=max(0, request_deadline - time.monotonic()))
        except queue.Empty:
            if stream:
                try:
                    stream[0].shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            raise ManagedFailure("request_timeout") from None
        if not success:
            if isinstance(outcome, ManagedFailure):
                raise outcome
            if isinstance(outcome, (TimeoutError, socket.timeout)):
                raise ManagedFailure("request_timeout") from None
            raise ManagedFailure("transport_failed") from None
        status, raw = outcome
        if status < 200 or status >= 300:
            raise ManagedFailure("provider_http_error", providers.analyze_response(
                "gemini", status, raw, providers.MODELS[0]))
        return raw

    def json(self, method, path, payload=None):
        raw = self.send(method, path, payload)
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeError):
            raise ManagedFailure("invalid_json_response") from None
        if not isinstance(value, dict):
            raise ManagedFailure("unexpected_response_shape")
        return value


def interaction_state(value, expected_id=None):
    identifier = resource_id(value.get("id"))
    if expected_id is not None and identifier != expected_id:
        raise ManagedFailure("interaction_identity_changed")
    state = value.get("status")
    if not isinstance(state, str) or state not in providers.INTERACTION_STATES:
        raise ManagedFailure("unknown_interaction_status")
    if value.get("agent") is not None and value["agent"] != AGENT:
        raise ManagedFailure("unexpected_agent")
    return identifier, state


def execution_evidence(interaction):
    steps = interaction.get("steps")
    if not isinstance(steps, list):
        raise ManagedFailure("unexpected_response_shape")
    calls, matches = {}, set()
    counts = {name: 0 for name in ("code_execution_call", "code_execution_result",
                                  "function_call", "function_result", "model_output", "other")}
    for step in steps:
        if not isinstance(step, dict):
            continue
        kind = step.get("type")
        counts[kind if isinstance(kind, str) and kind in counts else "other"] += 1
        if kind == "code_execution_call":
            arguments = step.get("arguments")
            identifier = step.get("id")
            code = arguments.get("code") if isinstance(arguments, dict) else None
            if isinstance(identifier, str) and isinstance(code, str) and SOURCE_PATH in code:
                calls[identifier] = True
    for step in steps:
        if not isinstance(step, dict) or step.get("type") != "code_execution_result":
            continue
        identifier, output = step.get("call_id"), step.get("result")
        if (isinstance(identifier, str) and identifier in calls and isinstance(output, str)
                and ("is_error" not in step or step["is_error"] is False)
                and MARKER in [line.strip() for line in output.splitlines()]):
            matches.add(identifier)
    return {"step_counts": counts, "matched_execution_count": len(matches),
            "command_reference_observed": bool(calls), "execution_marker_observed": bool(matches)}


def select_artifact(listing):
    files = listing.get("files")
    if not isinstance(files, list):
        raise ManagedFailure("unexpected_response_shape")
    paths = [entry.get("path") for entry in files if isinstance(entry, dict)
             and entry.get("type") == "FILE"
             and entry.get("path") in (ARTIFACT_NAME, "workspace/" + ARTIFACT_NAME)]
    if not paths:
        raise ManagedFailure("artifact_not_found")
    if len(paths) != 1:
        raise ManagedFailure("artifact_path_ambiguous")
    return paths[0]


def safe_usage(interaction):
    usage = interaction.get("usage")
    if not isinstance(usage, dict):
        return {}
    return {field: usage[field] for field in USAGE_FIELDS
            if type(usage.get(field)) is int and 0 <= usage[field] <= 10**12}


def run_job(key, timeout, emit=None, transport_factory=Transport, max_total_tokens=4096):
    started = time.monotonic()
    final_deadline = started + timeout
    work_deadline = final_deadline - 10
    transport = transport_factory(key, work_deadline)
    identifier, state, create_sent, create_rejected = None, None, False, False
    report = {"result": "not_started", "agent": AGENT, "token_budget": max_total_tokens,
              "interaction_status": "not_tested", "artifact_downloaded": False,
              "content_match": False, "cancellation": "not_needed"}
    try:
        report["phase"] = "create"
        value = transport.json("POST", "/v1beta/interactions", create_payload(max_total_tokens))
        create_sent = True
        # Retain a valid ID for cancellation even if the remaining shape is invalid.
        identifier = resource_id(value.get("id"))
        identifier, state = interaction_state(value)
        last_notice = 0
        while True:
            report["interaction_status"] = state
            if emit is not None and (time.monotonic() - last_notice >= 20 or state in TERMINAL):
                emit({"event": "managed_probe_progress", "state": state})
                last_notice = time.monotonic()
            if state not in {"queued", "in_progress"}:
                break
            report["phase"] = "poll"
            remaining = work_deadline - time.monotonic()
            if remaining <= 0:
                raise ManagedFailure("job_deadline")
            time.sleep(min(2, remaining))
            value = transport.json("GET", "/v1beta/interactions/" + identifier)
            identifier, state = interaction_state(value, identifier)
        report["usage"] = safe_usage(value)
        report["execution_steps_present"] = isinstance(value.get("steps"), list)
        if report["execution_steps_present"]:
            report.update(execution_evidence(value))
        if state != "completed":
            if state == "incomplete":
                # Current Interactions schema has no incomplete_details/reason.
                report["incomplete_reason"] = "unclassified"
            raise ManagedFailure("interaction_not_completed")
        if not report["execution_steps_present"]:
            raise ManagedFailure("unexpected_response_shape")
        environment_id = resource_id(value.get("environment_id"))
        prefix = "/v1beta/environments/" + environment_id + "/files"
        report["phase"] = "list_artifact"
        listing = transport.json("GET", prefix + "?recursive=true")
        artifact_path = select_artifact(listing)
        report["phase"] = "download_artifact"
        content = transport.send("GET", prefix + "/" + artifact_path + "?alt=media", limit=4096)
        report.update(artifact_downloaded=True, artifact_bytes=len(content),
                      artifact_sha256=hashlib.sha256(content).hexdigest(),
                      expected_sha256=EXPECTED_HASH, content_match=content == EXPECTED)
        if not report["content_match"]:
            raise ManagedFailure("artifact_content_mismatch")
        if not report["execution_marker_observed"]:
            raise ManagedFailure("execution_evidence_missing")
        report.update(result="passed", phase="complete")
    except ManagedFailure as exc:
        report["result"] = exc.args[0]
        if exc.provider_error is not None:
            report["provider_error"] = exc.provider_error
            create_rejected = (report["phase"] == "create" and
                               exc.provider_error.get("http_status") in {400, 401, 403, 404, 429})
    except KeyboardInterrupt:
        report["result"] = "interrupted"
    except Exception:
        report["result"] = "internal_probe_error"
    finally:
        create_sent = create_sent or transport.requests_sent > 0
        if identifier and state not in TERMINAL:
            report["cancellation"] = "unconfirmed"
            try:
                transport.deadline = final_deadline
                cancelled = transport.json("POST", "/v1beta/interactions/" + identifier + ":cancel")
                cancelled_id, cancelled_state = interaction_state(cancelled, identifier)
                if cancelled_state == "cancelled":
                    report["cancellation"] = "confirmed"
                elif cancelled_state in TERMINAL:
                    report["cancellation"] = "already_terminal"
            except (Exception, KeyboardInterrupt):
                pass
        report["remote_job_may_continue"] = bool(create_sent and not create_rejected and state not in TERMINAL
            and report["cancellation"] not in {"confirmed", "already_terminal"})
    report["network"] = transport.network
    report["requests_sent"] = transport.requests_sent
    report["elapsed_ms"] = round((time.monotonic() - started) * 1000)
    report["observed_at_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    report["not_tested"] = ["generated_app", "repair_loop", "gradium_speech", "physical_device"]
    return report


def self_test():
    """All fixtures are synthetic; these tests never use provider credentials."""
    import copy
    import unittest
    from unittest import mock

    def completed():
        return {"id": "test_interaction", "agent": AGENT, "status": "completed",
                "environment_id": "test_environment", "steps": [
                    {"type": "code_execution_call", "id": "test_call",
                     "arguments": {"code": "exec(open('" + SOURCE_PATH + "').read())"}},
                    {"type": "code_execution_result", "call_id": "test_call", "result": MARKER + "\n"}]}

    class FakeTransport:
        def __init__(self, key, deadline):
            self.deadline, self.requests_sent = deadline, 0
            self.network = {"result": "synthetic"}
            self.interaction, self.content = completed(), EXPECTED
            self.routes = []

        def json(self, method, path, payload=None):
            self.requests_sent += 1
            self.routes.append((method, path))
            if path.endswith(":cancel"):
                return dict(self.interaction, status="cancelled")
            if "/files" in path:
                return {"files": [{"type": "FILE", "path": "workspace/" + ARTIFACT_NAME}]}
            return copy.deepcopy(self.interaction)

        def send(self, method, path, payload=None, limit=MAX_JSON):
            self.requests_sent += 1
            self.routes.append((method, path))
            return self.content

    class ManagedTests(unittest.TestCase):
        def test_payload_has_only_fixed_public_input_and_restricted_tools(self):
            with mock.patch.dict(providers.os.environ, {"GEMINI_API_KEY": "synthetic-private-value"}):
                payload = create_payload()
            self.assertNotIn("synthetic-private-value", json.dumps(payload))
            self.assertEqual(payload["environment"]["network"], "disabled")
            self.assertEqual(payload["tools"], [{"type": "code_execution"}])
            self.assertEqual(payload["environment"]["sources"][0]["content"], SOURCE)
            self.assertNotIn(ARTIFACT_NAME, payload["environment"]["sources"][0]["target"])

        def test_generated_prose_cannot_prove_execution(self):
            value = completed()
            value["steps"] = [{"type": "model_output", "content": [{"type": "text", "text": MARKER}]}]
            self.assertFalse(execution_evidence(value)["execution_marker_observed"])
            value = completed()
            value["steps"][1]["call_id"] = "unmatched"
            self.assertFalse(execution_evidence(value)["execution_marker_observed"])
            value["steps"][1].update(call_id="test_call", is_error=True)
            self.assertFalse(execution_evidence(value)["execution_marker_observed"])

        def test_end_to_end_fixture_pass_requires_download_and_trace(self):
            transport = FakeTransport("unused", 0)
            report = run_job("synthetic-private-value", 60, transport_factory=lambda *args: transport)
            self.assertEqual(report["result"], "passed")
            self.assertEqual(report["artifact_sha256"], EXPECTED_HASH)
            self.assertEqual(transport.routes[-1][1], "/v1beta/environments/test_environment/files/workspace/" + ARTIFACT_NAME + "?alt=media")
            self.assertNotIn("test_environment", json.dumps(report))
            self.assertNotIn("synthetic-private-value", json.dumps(report))
            transport.content = b"different"
            report = run_job("unused", 60, transport_factory=lambda *args: transport)
            self.assertEqual(report["result"], "artifact_content_mismatch")
            transport.content = EXPECTED
            transport.interaction["steps"] = []
            self.assertEqual(run_job("unused", 60, transport_factory=lambda *args: transport)["result"],
                             "execution_evidence_missing")

        def test_resource_and_artifact_paths_cannot_escape_routes(self):
            for value in ("../x", "secret?key=value", "https://elsewhere", "bad\nvalue", None):
                with self.assertRaises(ManagedFailure):
                    resource_id(value)
            self.assertFalse(allowed_route("GET", "https://elsewhere"))
            self.assertFalse(allowed_route("GET", "/v1beta/environments/e/files/../private?alt=media"))
            with self.assertRaisesRegex(ManagedFailure, "artifact_not_found"):
                select_artifact({"files": [{"type": "FILE", "path": "../" + ARTIFACT_NAME}]})
            with self.assertRaisesRegex(ManagedFailure, "artifact_path_ambiguous"):
                select_artifact({"files": [{"type": "FILE", "path": ARTIFACT_NAME}] * 2})

        def test_cancel_route_requires_post_colon_action_and_valid_id(self):
            path = "/v1beta/interactions/test_Interaction-123:cancel"
            self.assertTrue(allowed_route("POST", path))
            invalid = [("GET", path), ("DELETE", path),
                       ("POST", "/v1beta/interactions/test_Interaction-123/cancel"),
                       ("POST", "/v1beta/interactions/:cancel"),
                       ("POST", "/v1beta/interactions/../other:cancel"),
                       ("POST", "/v1beta/interactions/id%3Acancel"),
                       ("POST", path + "?redirect=other"),
                       ("POST", "/v1beta/interactions/" + "i" * 4097 + ":cancel")]
            for method, route in invalid:
                with self.subTest(method=method, path=route):
                    self.assertFalse(allowed_route(method, route))
                    with mock.patch.object(providers, "network_preflight") as preflight, \
                            self.assertRaisesRegex(ManagedFailure, "invalid_route"):
                        Transport("synthetic", time.monotonic() + 1).send(method, route, {})
                    preflight.assert_not_called()

        def test_incomplete_state_never_downloads_or_passes(self):
            transport = FakeTransport("unused", 0)
            transport.interaction["status"] = "incomplete"
            transport.interaction["usage"] = {
                "total_tokens": 4100, "total_input_tokens": 4000,
                "total_output_tokens": 100, "total_cached_tokens": 0,
                "private_metadata": "synthetic-private-value"}
            transport.interaction["incomplete_details"] = {"reason": "synthetic-private-value"}
            report = run_job("unused", 60, transport_factory=lambda *args: transport)
            self.assertEqual(report["result"], "interaction_not_completed")
            self.assertFalse(report["artifact_downloaded"])
            self.assertEqual(len(transport.routes), 1)
            self.assertEqual(report["usage"]["total_tokens"], 4100)
            self.assertEqual(report["step_counts"]["code_execution_call"], 1)
            self.assertEqual(report["incomplete_reason"], "unclassified")
            self.assertNotIn("synthetic-private-value", json.dumps(report))

        def test_usage_is_numeric_allowlist_and_token_budget_is_explicit(self):
            value = {"usage": {"total_tokens": True, "total_input_tokens": -1,
                               "total_output_tokens": "synthetic-private-value",
                               "total_cached_tokens": 10**13, "total_thought_tokens": 7}}
            self.assertEqual(safe_usage(value), {"total_thought_tokens": 7})
            self.assertEqual(safe_usage({}), {})
            self.assertEqual(create_payload(16384)["agent_config"]["max_total_tokens"], 16384)
            transport = FakeTransport("unused", 0)
            report = run_job("unused", 60, transport_factory=lambda *args: transport, max_total_tokens=16384)
            self.assertEqual(report["token_budget"], 16384)
            self.assertEqual(report["result"], "passed")

        def test_deadline_attempts_cancellation_within_reserved_time(self):
            transport = FakeTransport("unused", 0)
            transport.interaction["status"] = "in_progress"
            report = run_job("unused", 0.1, transport_factory=lambda *args: transport)
            self.assertEqual(report["result"], "job_deadline")
            self.assertEqual(report["cancellation"], "confirmed")
            self.assertFalse(report["remote_job_may_continue"])
            self.assertTrue(transport.routes[-1][1].endswith(":cancel"))

        def test_network_failure_sends_no_authenticated_request(self):
            with mock.patch.object(providers, "network_preflight", return_value=(None, {"result": "dns_unavailable"})) as preflight:
                report = run_job("synthetic-private-value", 60)
            self.assertEqual(preflight.call_count, 1)
            self.assertEqual(report["result"], "network_unavailable")
            self.assertEqual(report["requests_sent"], 0)
            self.assertFalse(report["remote_job_may_continue"])
            self.assertNotIn("synthetic-private-value", json.dumps(report))

        def test_transport_timeout_interrupts_headers_without_retry(self):
            released = threading.Event()
            connection = mock.Mock()

            def stalled_headers():
                released.wait(1)
                raise OSError("synthetic-private-value")

            connection.getresponse.side_effect = stalled_headers
            connection.sock.shutdown.side_effect = lambda how: released.set()
            transport = Transport("synthetic-private-value", time.monotonic() + 0.05)
            try:
                with mock.patch.object(providers, "network_preflight", return_value=(connection, {"result": "passed"})):
                    with self.assertRaisesRegex(ManagedFailure, "request_timeout"):
                        transport.send("POST", "/v1beta/interactions", create_payload())
                connection.request.assert_called_once()
                connection.sock.shutdown.assert_called_once_with(socket.SHUT_RDWR)
            finally:
                released.set()

        def test_response_bound_and_provider_error_redaction(self):
            connection, response = mock.Mock(), mock.Mock(status=400)
            response.read1.side_effect = [json.dumps({"error": {"status": "INVALID_ARGUMENT", "message": "synthetic-private-value"}}).encode(), b""]
            connection.getresponse.return_value = response
            transport = Transport("synthetic-private-value", time.monotonic() + 1)
            with mock.patch.object(providers, "network_preflight", return_value=(connection, {"result": "passed"})):
                with self.assertRaises(ManagedFailure) as caught:
                    transport.send("POST", "/v1beta/interactions", create_payload())
                self.assertNotIn("synthetic-private-value", json.dumps(caught.exception.provider_error))
                response.read1.side_effect = None
                response.read1.return_value = b"x" * 100
                with self.assertRaisesRegex(ManagedFailure, "response_too_large"):
                    transport.send("POST", "/v1beta/interactions", create_payload(), limit=10)

    print("UNIT-ONLY: synthetic fixtures; no managed-agent access or artifact retrieval established.")
    outcome = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(ManagedTests))
    return 0 if outcome.wasSuccessful() else 1


def main(argv=None):
    parser = providers.SafeParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="create one real, quota-consuming managed job")
    parser.add_argument("--self-test", action="store_true", help="synthetic tests; no credentials or network")
    parser.add_argument("--job-timeout", type=float, default=180, help="whole local job budget including cancellation, seconds (30–300)")
    parser.add_argument("--max-total-tokens", type=int, choices=TOKEN_BUDGETS, default=4096,
                        help="explicit managed-agent token budget; no automatic escalation")
    args = parser.parse_args(argv)
    if not 30 <= args.job_timeout <= 300 or (args.live and args.self_test):
        parser.error("invalid mode or deadline")
    if args.self_test:
        return self_test()
    if not args.live:
        print('{"result":"live_not_requested","requests_sent":0}')
        return 0
    try:
        key = providers.load_keys(providers.ROOT / ".env")["gemini"]
    except providers.ProbeError as exc:
        print(json.dumps({"result": exc.args[0], "requests_sent": 0}))
        return 2
    if not key:
        print('{"result":"blocked_by_missing_key","requests_sent":0}')
        return 1
    report = run_job(key, args.job_timeout, emit=lambda event: print(json.dumps(event), flush=True),
                     max_total_tokens=args.max_total_tokens)
    print(json.dumps(report, indent=2))
    return 0 if report["result"] == "passed" else (130 if report["result"] == "interrupted" else 1)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('{"result":"interrupted","remote_job_state":"unverified"}')
        sys.exit(130)
    except Exception:
        print('{"result":"internal_probe_error","details":"omitted"}')
        sys.exit(2)
