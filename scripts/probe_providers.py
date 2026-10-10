#!/usr/bin/env python3
"""Safely probe configured Gemini/Gradium access using Python 3.9+ stdlib.

Default: configuration presence plus direct DNS/TLS, without authentication.
--live: additionally make one tiny Gemini request and/or one Gradium credit GET.
--self-test: isolated synthetic tests only; no .env access or network activity.
Output deliberately excludes credentials, raw responses and exception messages.
"""

import argparse
import datetime
import http.client
import json
import os
from pathlib import Path
import queue
import shlex
import socket
import ssl
import sys
import threading
import time


ROOT = Path(__file__).resolve().parent.parent
MAX_RESPONSE_BYTES = 65536
KEY_NAMES = {"gemini": "GEMINI_API_KEY", "gradium": "GRADIUM_API_KEY"}
HOSTS = {"gemini": "generativelanguage.googleapis.com", "gradium": "api.gradium.ai"}
MODELS = ("gemini-3.8-flash", "gemini-3.5-flash-lite")
INTERACTION_STATES = {
    "queued", "in_progress", "requires_action", "completed",
    "failed", "cancelled", "incomplete",
}
GOOGLE_ERROR_STATUSES = {
    "INVALID_ARGUMENT", "FAILED_PRECONDITION", "OUT_OF_RANGE", "UNAUTHENTICATED",
    "PERMISSION_DENIED", "NOT_FOUND", "ALREADY_EXISTS", "RESOURCE_EXHAUSTED",
    "CANCELLED", "DATA_LOSS", "UNKNOWN", "INTERNAL", "UNAVAILABLE",
    "DEADLINE_EXCEEDED", "ABORTED", "UNIMPLEMENTED",
}
# Source: googleapis/googleapis, google/api/error_reason.proto. Unknown reasons,
# messages, domains and metadata must never become diagnostic output.
GOOGLE_ERROR_REASONS = {
    "API_KEY_INVALID": "api_key_invalid_or_expired",
    "API_KEY_SERVICE_BLOCKED": "api_key_service_blocked",
    "API_KEY_HTTP_REFERRER_BLOCKED": "api_key_application_blocked",
    "API_KEY_IP_ADDRESS_BLOCKED": "api_key_application_blocked",
    "API_KEY_ANDROID_APP_BLOCKED": "api_key_application_blocked",
    "API_KEY_IOS_APP_BLOCKED": "api_key_application_blocked",
    "SERVICE_DISABLED": "service_disabled",
    "BILLING_DISABLED": "billing_disabled",
    "RATE_LIMIT_EXCEEDED": "quota_or_rate_limit",
    "RESOURCE_QUOTA_EXCEEDED": "quota_or_rate_limit",
}
SAFE_ERROR_CODES = {
    "configuration_unreadable", "configuration_too_large",
    "configuration_invalid_encoding", "configuration_duplicate_key",
    "configuration_invalid_value", "configuration_invalid_key_characters",
    "dns_timeout", "dns_unavailable", "request_timeout", "response_too_large",
}


class ProbeError(Exception):
    """Only application-owned fixed diagnostic codes belong in this exception."""

    def __init__(self, code):
        super().__init__(code if code in SAFE_ERROR_CODES else "internal_probe_error")


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's normal message can echo private command-line input.
        self.exit(2, "Invalid arguments. Run --help; never pass API keys as arguments.\n")


def load_keys(env_path):
    """Parse only the two supported names; never evaluate shell expressions."""
    values = {}
    try:
        with env_path.open("rb") as source:
            raw = source.read(65537)
    except FileNotFoundError:
        raw = b""
    except OSError:
        raise ProbeError("configuration_unreadable") from None
    if len(raw) > 65536:
        raise ProbeError("configuration_too_large")
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeError:
        raise ProbeError("configuration_invalid_encoding") from None
    for line in lines:
        name, separator, value = line.partition("=")
        name = name.strip()
        if name.startswith("export "):
            name = name[7:].strip()
        if not separator or name not in KEY_NAMES.values():
            continue
        if name in values:
            raise ProbeError("configuration_duplicate_key")
        try:
            parts = shlex.split(value, comments=True, posix=True)
        except ValueError:
            raise ProbeError("configuration_invalid_value") from None
        if len(parts) > 1:
            raise ProbeError("configuration_invalid_value")
        values[name] = parts[0] if parts else ""
    keys = {}
    for provider, name in KEY_NAMES.items():
        value = os.environ.get(name, values.get(name, ""))
        if len(value) > 4096 or any(ord(char) < 33 or ord(char) > 126 for char in value):
            raise ProbeError("configuration_invalid_key_characters")
        keys[provider] = value
    return keys


def resolve_once(host, timeout):
    """Bound caller waiting for the OS resolver without retrying DNS."""
    results = queue.Queue(maxsize=1)

    def resolve():
        try:
            results.put((True, socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)))
        except Exception:
            results.put((False, None))

    threading.Thread(target=resolve, daemon=True).start()
    try:
        success, addresses = results.get(timeout=timeout)
    except queue.Empty:
        raise ProbeError("dns_timeout") from None
    if not success or not addresses:
        raise ProbeError("dns_unavailable")
    return addresses


def network_preflight(host, timeout):
    """Return a verified connection for reuse; no credential has been sent."""
    deadline = time.monotonic() + timeout
    network = {"dns": "not_tested", "tls": "not_tested"}
    try:
        addresses = resolve_once(host, timeout)
    except ProbeError as exc:
        network.update(dns="failed", result=exc.args[0])
        return None, network
    network["dns"] = "passed"
    context = ssl.create_default_context()
    seen = set()
    failure = "connection_unavailable"
    for family, socktype, protocol, _canonical, address in addresses:
        identity = (family, address)
        if identity in seen:
            continue
        seen.add(identity)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            failure = "network_timeout"
            break
        raw = None
        try:
            raw = socket.socket(family, socktype, protocol)
            # Several resolved addresses may be tried within this one budget.
            raw.settimeout(min(remaining, 3.0))
            raw.connect(address)
            raw.settimeout(max(0.01, deadline - time.monotonic()))
            secured = context.wrap_socket(raw, server_hostname=host)
            raw = None
            connection = http.client.HTTPSConnection(host, timeout=timeout, context=context)
            connection.sock = secured
            network.update(tls="passed", result="passed")
            return connection, network
        except ssl.SSLCertVerificationError:
            failure = "tls_certificate_rejected"
            break
        except ssl.SSLError:
            failure = "tls_failed"
            break
        except (TimeoutError, socket.timeout):
            failure = "network_timeout"
        except OSError:
            failure = "connection_unavailable"
        finally:
            if raw is not None:
                raw.close()
    network.update(tls="failed", result=failure)
    return None, network


def request_once(connection, provider, key, model, timeout):
    """Bound the complete HTTP exchange, including slowly arriving headers."""
    deadline = time.monotonic() + timeout
    raw_socket = connection.sock
    results = queue.Queue(maxsize=1)

    def exchange():
        try:
            results.put((True, _request_exchange(connection, provider, key, model, deadline)))
        except Exception as exc:
            # Exceptions remain local; probe() emits only fixed diagnostic codes.
            results.put((False, exc))

    threading.Thread(target=exchange, daemon=True).start()
    try:
        success, result = results.get(timeout=max(0, deadline - time.monotonic()))
    except queue.Empty:
        # close() alone may defer closing a socket owned by HTTPResponse.makefile.
        # Shutdown interrupts the underlying stream even during header parsing.
        try:
            raw_socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        raise ProbeError("request_timeout") from None
    if not success:
        raise result
    return result


def _request_exchange(connection, provider, key, model, deadline):
    """Use only fixed official routes; no redirect, proxy, or retry handling."""
    headers = {"Accept": "application/json", "Connection": "close"}
    if provider == "gemini":
        method, path = "POST", "/v1beta/interactions"
        headers.update({"x-goog-api-key": key, "Content-Type": "application/json"})
        body = json.dumps({
            "model": model,
            "input": "Reply with exactly READY and nothing else.",
            "store": False,
            "generation_config": {"max_output_tokens": 64},
        }).encode("utf-8")
    else:
        method, path, body = "GET", "/api/usages/credits", None
        headers["x-api-key"] = key
    raw_socket = connection.sock
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ProbeError("request_timeout")
    raw_socket.settimeout(remaining)
    connection.request(method, path, body=body, headers=headers)
    raw_socket.settimeout(max(0.01, deadline - time.monotonic()))
    response = connection.getresponse()
    # Keep the original socket reference: getresponse can detach it from the
    # connection, while HTTPResponse's file object still owns the open socket.
    try:
        chunks, size = [], 0
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProbeError("request_timeout")
            raw_socket.settimeout(remaining)
            chunk = response.read1(min(4096, MAX_RESPONSE_BYTES + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > MAX_RESPONSE_BYTES:
                raise ProbeError("response_too_large")
        return response.status, b"".join(chunks)
    finally:
        response.close()


def google_error_diagnostics(raw):
    """Allowlist structured status/reason; never inspect or emit free text."""
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError):
        return {}
    error = data.get("error") if isinstance(data, dict) else None
    if not isinstance(error, dict):
        return {}
    diagnostics = {}
    status = error.get("status")
    if isinstance(status, str) and status in GOOGLE_ERROR_STATUSES:
        diagnostics["google_error_status"] = status
    details = error.get("details")
    if not isinstance(details, list):
        return diagnostics
    for detail in details:
        if not isinstance(detail, dict):
            continue
        if (detail.get("@type") != "type.googleapis.com/google.rpc.ErrorInfo"
                or detail.get("domain") != "googleapis.com"):
            continue
        reason = detail.get("reason")
        if isinstance(reason, str) and reason in GOOGLE_ERROR_REASONS:
            diagnostics.update(google_error_reason=reason, result=GOOGLE_ERROR_REASONS[reason])
            break
    return diagnostics


def analyze_response(provider, status, raw, model):
    """Reduce untrusted provider data to fixed codes and booleans only."""
    result = {"http_status": status, "authentication": "unverified"}
    if status < 200 or status >= 300:
        code = {
            400: "request_rejected", 401: "authentication_rejected",
            403: "permission_rejected", 404: "route_or_model_unavailable",
            429: "quota_or_rate_limit",
        }.get(status, "provider_http_error")
        if 300 <= status < 400:
            code = "redirect_refused"
        if provider == "gradium" and status == 500 and b"error from server 1008:" in raw:
            code = "policy_or_authentication_rejected"
        result["result"] = code
        if provider == "gemini":
            result.update(google_error_diagnostics(raw))
        return result
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError):
        result["result"] = "invalid_json_response"
        return result
    if not isinstance(data, dict):
        result["result"] = "unexpected_response_shape"
        return result
    if provider == "gradium":
        remaining = data.get("remaining_credits")
        allocated = data.get("allocated_credits")
        if type(remaining) is not int or type(allocated) is not int or allocated < 0:
            result["result"] = "unexpected_credit_response"
            return result
        result.update(authentication="confirmed", credits_available=remaining > 0,
                      result="passed" if remaining > 0 else "authenticated_no_credits")
        return result
    state = data.get("status")
    if not isinstance(state, str) or state not in INTERACTION_STATES:
        result["result"] = "unknown_interaction_status"
        return result
    result.update(interaction_status=state, authentication="confirmed")
    if state != "completed":
        result["result"] = "interaction_not_completed"
        return result
    if data.get("model") != model:
        result["result"] = "unexpected_model_response"
        return result
    parts = []
    steps = data.get("steps")
    if not isinstance(steps, list):
        result["result"] = "unexpected_response_shape"
        return result
    for step in steps:
        if not isinstance(step, dict) or step.get("type") != "model_output":
            continue
        content = step.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str):
                parts.append(part["text"])
    result["expected_reply"] = "".join(parts).strip() == "READY"
    result["result"] = "passed" if result["expected_reply"] else "unexpected_model_output"
    return result


def probe(provider, key, live, model, network_timeout, request_timeout):
    started = time.monotonic()
    result = {"provider": provider, "credential": "configured" if key else "missing",
              "authentication": "not_tested", "result": "not_started"}
    connection = None
    try:
        connection, network = network_preflight(HOSTS[provider], network_timeout)
        result["network"] = network
        if connection is None:
            result["result"] = "blocked_by_network"
        elif not key:
            result["result"] = "blocked_by_missing_key"
        elif not live:
            result["result"] = "network_ready_live_not_requested"
        else:
            status, raw = request_once(connection, provider, key, model, request_timeout)
            result.update(analyze_response(provider, status, raw, model))
    except ProbeError as exc:
        result["result"] = exc.args[0]
    except (TimeoutError, socket.timeout):
        result["result"] = "request_timeout"
    except ssl.SSLError:
        result["result"] = "tls_failed"
    except (OSError, http.client.HTTPException):
        result["result"] = "request_transport_failed"
    except Exception:
        # Includes malformed peer responses and header errors; never repr(exc).
        result["result"] = "internal_probe_error"
    finally:
        if connection is not None:
            connection.close()
    result["elapsed_ms"] = round((time.monotonic() - started) * 1000)
    return result


def self_test():
    """Synthetic protocol/failure tests, explicitly not provider evidence."""
    import contextlib
    import io
    import tempfile
    import unittest
    from unittest import mock

    class ProbeTests(unittest.TestCase):
        def test_key_parsing_and_environment_precedence(self):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "private-config"
                path.write_text('export GEMINI_API_KEY="file-value"\nGRADIUM_API_KEY=voice-value # comment\n')
                with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "process-value"}, clear=True):
                    self.assertEqual(load_keys(path), {"gemini": "process-value", "gradium": "voice-value"})
                path.write_text('GEMINI_API_KEY="unterminated\n')
                with self.assertRaises(ProbeError):
                    load_keys(path)

        def test_header_injection_rejected(self):
            with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "private\nvalue"}, clear=True):
                with self.assertRaises(ProbeError):
                    load_keys(Path("/nonexistent-provider-probe-test-file"))

        def test_network_failure_stops_authenticated_call(self):
            with mock.patch(__name__ + ".network_preflight", return_value=(None, {"result": "dns_unavailable"})), \
                    mock.patch(__name__ + ".request_once") as request:
                result = probe("gemini", "synthetic-private-value", True, MODELS[0], 1, 1)
                request.assert_not_called()
                self.assertEqual(result["result"], "blocked_by_network")

        def test_default_never_authenticates(self):
            connection = mock.Mock()
            with mock.patch(__name__ + ".network_preflight", return_value=(connection, {"result": "passed"})), \
                    mock.patch(__name__ + ".request_once") as request:
                result = probe("gradium", "synthetic-private-value", False, MODELS[0], 1, 1)
                request.assert_not_called()
                self.assertEqual(result["authentication"], "not_tested")
                connection.close.assert_called_once()

        def test_safe_exceptions(self):
            connection = mock.Mock()
            with mock.patch(__name__ + ".network_preflight", return_value=(connection, {"result": "passed"})), \
                    mock.patch(__name__ + ".request_once", side_effect=RuntimeError("synthetic-private-value")):
                result = probe("gemini", "synthetic-private-value", True, MODELS[0], 1, 1)
                self.assertNotIn("synthetic-private-value", json.dumps(result))
                self.assertEqual(result["result"], "internal_probe_error")
            self.assertEqual(str(ProbeError("synthetic-private-value")), "internal_probe_error")

        def test_dns_is_attempted_once_and_failure_is_safe(self):
            with mock.patch.object(socket, "getaddrinfo", side_effect=socket.gaierror("synthetic-private-value")) as lookup:
                connection, result = network_preflight(HOSTS["gemini"], 1)
                self.assertIsNone(connection)
                lookup.assert_called_once()
                self.assertEqual(result["result"], "dns_unavailable")
                self.assertNotIn("synthetic-private-value", json.dumps(result))

        def test_dns_wait_is_bounded(self):
            released = threading.Event()

            def stalled_lookup(*args, **kwargs):
                released.wait(1)
                return []

            try:
                with mock.patch.object(socket, "getaddrinfo", side_effect=stalled_lookup):
                    with self.assertRaisesRegex(ProbeError, "dns_timeout"):
                        resolve_once(HOSTS["gradium"], 0.01)
            finally:
                released.set()

        def test_certificate_failure_closes_socket(self):
            address = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.1", 443))]
            raw, context = mock.Mock(), mock.Mock()
            context.wrap_socket.side_effect = ssl.SSLCertVerificationError("synthetic-private-value")
            with mock.patch(__name__ + ".resolve_once", return_value=address), \
                    mock.patch.object(socket, "socket", return_value=raw), \
                    mock.patch.object(ssl, "create_default_context", return_value=context):
                connection, result = network_preflight(HOSTS["gradium"], 1)
                self.assertIsNone(connection)
                self.assertEqual(result["result"], "tls_certificate_rejected")
                raw.close.assert_called_once()

        def test_http_failure_does_not_echo_body(self):
            for status, expected in ((403, "permission_rejected"), (429, "quota_or_rate_limit"), (302, "redirect_refused")):
                result = analyze_response("gemini", status, b"synthetic-private-value", MODELS[0])
                self.assertEqual(result["result"], expected)
                self.assertNotIn("synthetic-private-value", json.dumps(result))

        def test_credit_shapes_and_zero_balance(self):
            for remaining, expected in ((12, "passed"), (0, "authenticated_no_credits"), (True, "unexpected_credit_response")):
                raw = json.dumps({"remaining_credits": remaining, "allocated_credits": 100}).encode()
                self.assertEqual(analyze_response("gradium", 200, raw, MODELS[0])["result"], expected)
            self.assertEqual(analyze_response("gradium", 200, b"not-json", MODELS[0])["result"], "invalid_json_response")

        def test_google_400_known_key_reason_is_classified_without_private_fields(self):
            for reason, expected in (("API_KEY_INVALID", "api_key_invalid_or_expired"),
                                     ("API_KEY_SERVICE_BLOCKED", "api_key_service_blocked")):
                raw = json.dumps({"error": {
                    "status": "INVALID_ARGUMENT", "message": "synthetic-private-value",
                    "details": [{"@type": "type.googleapis.com/google.rpc.ErrorInfo",
                                 "domain": "googleapis.com", "reason": reason,
                                 "metadata": {"consumer": "synthetic-private-value"}}],
                }}).encode()
                result = analyze_response("gemini", 400, raw, MODELS[0])
                self.assertEqual(result["result"], expected)
                self.assertEqual(result["google_error_status"], "INVALID_ARGUMENT")
                self.assertEqual(result["google_error_reason"], reason)
                self.assertEqual(result["authentication"], "unverified")
                self.assertNotIn("synthetic-private-value", json.dumps(result))

        def test_google_unknown_errors_never_echo_or_infer_key_failure(self):
            for status in ("INVALID_ARGUMENT", "synthetic-private-value", {}, None):
                for reason in ("synthetic-private-value", {}, None):
                    raw = json.dumps({"error": {
                        "status": status, "message": "synthetic-private-value",
                        "details": [{"@type": "type.googleapis.com/google.rpc.ErrorInfo",
                                     "domain": "googleapis.com", "reason": reason,
                                     "metadata": {"private": "synthetic-private-value"}}],
                    }}).encode()
                    result = analyze_response("gemini", 400, raw, MODELS[0])
                    self.assertEqual(result["result"], "request_rejected")
                    self.assertNotIn("google_error_reason", result)
                    self.assertNotIn("synthetic-private-value", json.dumps(result))
                    self.assertEqual(result.get("google_error_status"),
                                     "INVALID_ARGUMENT" if status == "INVALID_ARGUMENT" else None)

        def test_gemini_completion_and_marker(self):
            data = {"status": "completed", "model": MODELS[0], "steps": [
                {"type": "model_output", "content": [{"type": "text", "text": "READY"}]}]}
            self.assertEqual(analyze_response("gemini", 200, json.dumps(data).encode(), MODELS[0])["result"], "passed")
            data["status"] = "incomplete"
            self.assertEqual(analyze_response("gemini", 200, json.dumps(data).encode(), MODELS[0])["result"], "interaction_not_completed")
            data["status"] = "synthetic-private-value"
            result = analyze_response("gemini", 200, json.dumps(data).encode(), MODELS[0])
            self.assertNotIn("synthetic-private-value", json.dumps(result))
            self.assertEqual(result["result"], "unknown_interaction_status")

        def test_no_credentials_in_url_and_no_redirect_following(self):
            for provider in KEY_NAMES:
                response = mock.Mock(status=302)
                response.read1.side_effect = [b"synthetic-private-value", b""]
                connection = mock.Mock()
                connection.getresponse.return_value = response
                status, _raw = request_once(connection, provider, "synthetic-private-value", MODELS[0], 1)
                self.assertEqual(status, 302)
                self.assertEqual(connection.request.call_count, 1)
                args, kwargs = connection.request.call_args
                self.assertNotIn("synthetic-private-value", str(args))
                self.assertNotIn("synthetic-private-value", str(kwargs.get("body")))

        def test_response_size_bound(self):
            response = mock.Mock(status=200)
            response.read1.return_value = b"x" * 4096
            connection = mock.Mock()
            connection.getresponse.return_value = response
            with self.assertRaisesRegex(ProbeError, "response_too_large"):
                request_once(connection, "gradium", "synthetic-private-value", MODELS[0], 1)

        def test_slow_headers_obey_whole_request_deadline(self):
            released, completed = threading.Event(), threading.Event()
            connection = mock.Mock()

            def stalled_headers():
                try:
                    released.wait(2)
                    raise OSError("synthetic-private-value")
                finally:
                    completed.set()

            connection.getresponse.side_effect = stalled_headers
            connection.sock.shutdown.side_effect = lambda how: released.set()
            started = time.monotonic()
            try:
                with self.assertRaisesRegex(ProbeError, "request_timeout"):
                    request_once(connection, "gradium", "synthetic-private-value", MODELS[0], 0.05)
                self.assertLess(time.monotonic() - started, 0.5)
                connection.request.assert_called_once()
                connection.sock.shutdown.assert_called_once_with(socket.SHUT_RDWR)
                self.assertTrue(completed.wait(0.5))
            finally:
                released.set()

        def test_real_http_parser_handles_close_and_chunked_body(self):
            body = b'{"remaining_credits":12,"allocated_credits":100}'
            wire = (b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n"
                    + ("%x\r\n" % len(body)).encode() + body + b"\r\n0\r\n\r\n")

            class MemorySocket:
                def __init__(self):
                    self.request_bytes = bytearray()

                def sendall(self, data):
                    self.request_bytes.extend(data)

                def makefile(self, mode):
                    return io.BytesIO(wire)

                def settimeout(self, value):
                    pass

                def close(self):
                    pass

            connection = http.client.HTTPSConnection(HOSTS["gradium"])
            connection.sock = MemorySocket()
            status, received = request_once(connection, "gradium", "synthetic-private-value", MODELS[0], 1)
            self.assertEqual(status, 200)
            self.assertEqual(received, body)
            self.assertIsNone(connection.sock)

        def test_argument_error_does_not_echo_input(self):
            output = io.StringIO()
            with contextlib.redirect_stderr(output), self.assertRaises(SystemExit):
                SafeParser().parse_args(["--private-value", "synthetic-private-value"])
            self.assertNotIn("synthetic-private-value", output.getvalue())

    print("UNIT-ONLY: synthetic tests; no provider authentication, media, or hardware tested.")
    outcome = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(ProbeTests))
    return 0 if outcome.wasSuccessful() else 1


def main(argv=None):
    parser = SafeParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="send the selected minimal authenticated requests")
    parser.add_argument("--self-test", action="store_true", help="run synthetic tests without network or real credentials")
    parser.add_argument("--provider", choices=("all", "gemini", "gradium"), default="all")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env", help="private dotenv file; process environment takes precedence")
    parser.add_argument("--gemini-model", choices=MODELS, default=MODELS[0])
    parser.add_argument("--network-timeout", type=float, default=8, help="DNS/TLS budget per host, in seconds (1–30)")
    parser.add_argument("--request-timeout", type=float, default=30, help="authenticated request budget, in seconds (1–60)")
    args = parser.parse_args(argv)
    if not (1 <= args.network_timeout <= 30 and 1 <= args.request_timeout <= 60):
        parser.error("timeout outside supported range")
    if args.self_test:
        if args.live:
            parser.error("self-test and live are separate modes")
        return self_test()
    try:
        keys = load_keys(args.env_file)
    except ProbeError as exc:
        print(json.dumps({"result": exc.args[0], "authentication": "not_tested"}))
        return 2
    providers = list(KEY_NAMES) if args.provider == "all" else [args.provider]
    results = [probe(provider, keys[provider], args.live, args.gemini_model,
                     args.network_timeout, args.request_timeout) for provider in providers]
    print(json.dumps({
        "observed_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "mode": "live_minimal" if args.live else "network_only",
        "gemini_model": args.gemini_model if "gemini" in providers else None,
        "providers": results,
        "not_tested": ["gradium_speech_to_text", "gemini_media", "managed_agent_artifacts", "physical_device"],
    }, indent=2))
    success = "passed" if args.live else "network_ready_live_not_requested"
    return 0 if all(result["result"] == success for result in results) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('{"result":"interrupted","authentication":"unverified"}')
        sys.exit(130)
    except Exception:
        print('{"result":"internal_probe_error","details":"omitted"}')
        sys.exit(2)
