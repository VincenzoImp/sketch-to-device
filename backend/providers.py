"""Bounded REST calls for Gemini and Gradium; credentials never enter prompts."""

import io
import json
import queue
import re
import socket
import threading
import time
from urllib.parse import urlencode
import wave

from scripts.probe_providers import (HOSTS, ROOT, GOOGLE_ERROR_STATUSES, GOOGLE_ERROR_REASONS,
                                    ProbeError, analyze_response, load_keys, network_preflight)
from .media_limits import MAX_AUDIO_SECONDS


MODEL = "gemini-3.8-flash"
MANAGED_MODELS = ("gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite")
MANAGED_TOKEN_BUDGETS = (50000, 100000, 200000)
MANAGED_JOB_SECONDS = (180, 600)
# Fixed speech profiles; runtime vocabulary won the same-recording live comparison.
STT_CONFIGS = {
    "default": {"language": "en"},
    "runtime_context": {"language": "en", "delay_in_frames": 16,
                        "keywords": {"words": ["tap", "Tap", "timer", "Timer", "countdown", "Countdown",
                                               "score", "Score", "button", "Button", "toggle", "Toggle"],
                                     "boost": 2}},
}
STT_PATHS = {name: "/api/post/speech/asr?" + urlencode({"json_config": json.dumps(config, separators=(",", ":"))})
             for name, config in STT_CONFIGS.items()}
ERROR_MESSAGES = {
    "configuration": "Provider credentials are unavailable or invalid.",
    "network": "A provider could not be reached from the backend.",
    "deadline": "Generation exceeded its time limit.",
    "provider_auth": "A provider rejected the configured credentials or permissions.",
    "provider_quota": "Provider quota or rate limits prevented generation.",
    "provider_request": "A provider rejected the generation request.",
    "provider_response": "A provider returned an unsupported or incomplete response.",
    "provider_transport": "A provider connection ended before completion.",
    "input": "Provide a short request or a supported recording or image.",
    "media": "The attachment format could not be processed.",
    "media_limit": "Use at most three attachments, 20 MiB each and 32 MiB total; audio up to 60 seconds or video up to 30 seconds.",
    "media_tools": "FFmpeg and FFprobe are required for this recording format.",
    "speech": "Speech recognition did not complete. Try a clear English recording.",
    "tool_protocol": "The model did not complete the required validation tools.",
    "repair_limit": "The generated app failed validation after the repair limit.",
    "generation_stalled": "Generation repeated the same failed app. Your previous app is preserved.",
    "generation_superseded": "A newer request replaced this generation.",
    "generation_stopped": "Generation was stopped. Your installed app is preserved.",
    "generation": "The app could not be generated. Try a simpler supported request.",
    "unsupported_request": "This request needs a capability the device does not support yet. Your previous app is preserved.",
    "media_dimensions": "Use a photo with smaller pixel dimensions.",
    "media_size": "The attachment is too large. Choose a smaller file.",
    "media_duration": "Use audio up to 60 seconds or video up to 30 seconds.",
    "media_timeout": "The attachment took too long to process. Choose a smaller file.",
}
UNSUPPORTED_FEATURES = {"camera_capture", "microphone_recording", "speaker_playback", "network_requests",
                        "file_access", "gpio", "dynamic_text", "conditional_logic", "freeform_layout",
                        "runtime_limits"}
HTTP_CATEGORIES = {"request_rejected", "authentication_rejected", "permission_rejected",
                   "route_or_model_unavailable", "quota_or_rate_limit", "provider_http_error",
                   "redirect_refused", "policy_or_authentication_rejected"} | set(GOOGLE_ERROR_REASONS.values())
DIAGNOSTIC_REASONS = {
    "response_too_large", "invalid_json_response", "unexpected_response_shape",
    "invalid_resource_id", "unknown_interaction_status", "unexpected_agent",
    "interaction_identity_changed", "interaction_not_completed", "artifact_list_invalid",
    "artifact_not_found", "artifact_path_ambiguous", "validation_failed", "execution_evidence_missing",
    "token_budget_exhausted",
    "invalid_generation_profile", "validation_stalled",
}
DIAGNOSTIC_PHASES = {"create", "poll", "list_artifact", "download_artifact", "validate", "simulate", "execution"}
INTERACTION_STATES = {"queued", "in_progress", "requires_action", "completed", "failed", "cancelled", "incomplete"}
USAGE_FIELDS = {"total_input_tokens", "total_output_tokens", "total_thought_tokens",
                "total_cached_tokens", "total_tool_use_tokens", "total_tokens"}
RESEARCH_STEP_TYPES = {"google_search_call", "google_search_result", "url_context_call", "url_context_result"}
STEP_TYPES = {"code_execution_call", "code_execution_result", "function_call", "function_result", "model_output", "other"} | RESEARCH_STEP_TYPES


def safe_diagnostics(value):
    """Only fixed categories and bounded counters may leave provider handling."""
    if type(value) is not dict:
        return {}
    result = {}
    for name, allowed in (("phase", DIAGNOSTIC_PHASES), ("reason", DIAGNOSTIC_REASONS),
                          ("interaction_status", INTERACTION_STATES), ("http_category", HTTP_CATEGORIES),
                          ("google_error_status", GOOGLE_ERROR_STATUSES),
                          ("google_error_reason", set(GOOGLE_ERROR_REASONS)),
                          ("managed_model", set(MANAGED_MODELS)),
                          ("cancellation", {"not_needed", "not_attempted", "confirmed", "unconfirmed", "failed"})):
        if type(value.get(name)) is str and value[name] in allowed:
            result[name] = value[name]
    for name in ("attempt", "elapsed_ms", "token_budget", "effective_tokens", "artifact_matches", "poll_count",
                 "job_timeout_seconds", "repair_count", "stalled_failure_count"):
        if type(value.get(name)) is int and 0 <= value[name] <= 10**12:
            result[name] = value[name]
    if type(value.get("http_status")) is int and 100 <= value["http_status"] <= 599:
        result["http_status"] = value["http_status"]
    features = value.get("unsupported_features")
    if type(features) is list and len(features) <= len(UNSUPPORTED_FEATURES):
        result["unsupported_features"] = sorted({item for item in features
                                                  if type(item) is str and item in UNSUPPORTED_FEATURES})
    for name, allowed in (("usage", USAGE_FIELDS), ("step_counts", STEP_TYPES)):
        if type(value.get(name)) is dict:
            result[name] = {key: item for key, item in value[name].items()
                            if key in allowed and type(item) is int and 0 <= item <= 10**12}
    return result


class ProviderError(Exception):
    """Safe public failure; never wrap provider text or exception repr."""

    def __init__(self, code, diagnostics=None):
        self.code = code if code in ERROR_MESSAGES else "generation"
        self.message = ERROR_MESSAGES[self.code]
        self.diagnostics = safe_diagnostics(diagnostics)
        super().__init__(self.message)


def remaining(deadline, maximum=60):
    budget = min(maximum, deadline - time.monotonic())
    if budget <= 0:
        raise ProviderError("deadline")
    return budget


def _http_error(provider, status, raw):
    safe = analyze_response(provider, status, raw, MODEL)
    reason = safe.get("result")
    diagnostic = {"http_status": status, "http_category": reason,
                  "google_error_status": safe.get("google_error_status"),
                  "google_error_reason": safe.get("google_error_reason")}
    if status in (401, 403) or reason in {"api_key_invalid_or_expired", "api_key_service_blocked",
                                         "api_key_application_blocked", "service_disabled"}:
        return ProviderError("provider_auth", diagnostic)
    if status == 429 or reason in {"quota_or_rate_limit", "billing_disabled"}:
        return ProviderError("provider_quota", diagnostic)
    return ProviderError("provider_request", diagnostic)


def request(provider, key, path, body, content_type, deadline, max_response=524288, method="POST"):
    """One allowlisted request; bounded DNS/TLS/headers/body, no retry."""
    identifier = r"[A-Za-z0-9_-]{1,4096}"
    google_route = ((method == "POST" and (path == "/v1beta/interactions" or re.fullmatch(
        r"/v1beta/interactions/" + identifier + r"(?::cancel|/cancel)", path))) or
        (method == "GET" and (re.fullmatch(r"/v1beta/interactions/" + identifier, path) or re.fullmatch(
            r"/v1beta/environments/" + identifier + r"/files(?:\?recursive=true|/"
            r"(?:workspace/)?out/app\.json\?alt=media)", path))))
    allowed = (provider == "gemini" and google_route) or (
        provider == "gradium" and method == "POST" and path in STT_PATHS.values())
    if not allowed or not key or type(body) is not bytes or len(body) > 28 * 1024 * 1024:
        raise ProviderError("provider_request")
    end = time.monotonic() + remaining(deadline)
    outcomes, stream = queue.Queue(maxsize=1), []

    def exchange():
        connection = response = None
        try:
            connection, _network = network_preflight(HOSTS[provider], remaining(end, 8))
            if connection is None:
                raise ProviderError("network")
            raw_socket = connection.sock
            stream.append(raw_socket)
            raw_socket.settimeout(remaining(end))
            headers = {"Content-Type": content_type, "Connection": "close",
                       "Accept": "application/json" if provider == "gemini" else "application/x-ndjson",
                       "x-goog-api-key" if provider == "gemini" else "x-api-key": key}
            # The dedicated background-execution REST guide specifies this
            # revision and slash route; the older agent example uses :cancel.
            if provider == "gemini" and method == "POST" and path.endswith("/cancel"):
                headers["Api-Revision"] = "2026-05-20"
            connection.request(method, path, body=body if method == "POST" else None, headers=headers)
            response = connection.getresponse()
            size, chunks = 0, []
            while True:
                raw_socket.settimeout(remaining(end))
                chunk = response.read1(min(8192, max_response + 1 - size))
                if not chunk:
                    if response.length not in (None, 0):
                        raise ProviderError("provider_transport")
                    break
                size += len(chunk)
                if size > max_response:
                    raise ProviderError("provider_response", {"reason": "response_too_large"})
                chunks.append(chunk)
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
        success, outcome = outcomes.get(timeout=max(0, end - time.monotonic()))
    except queue.Empty:
        if stream:
            try:
                stream[0].shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        raise ProviderError("deadline") from None
    if not success:
        if isinstance(outcome, ProviderError):
            raise outcome
        raise ProviderError("provider_transport") from None
    status, raw = outcome
    if not 200 <= status < 300:
        raise _http_error(provider, status, raw)
    return raw


def parse_transcript(raw):
    """A complete HTTP body is required; any error event invalidates all text."""
    parts = []
    try:
        for line in raw.decode("utf-8").splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            if not isinstance(event, dict) or not isinstance(event.get("type"), str):
                raise ProviderError("speech")
            if event["type"] == "error":
                raise ProviderError("speech")
            if event["type"] == "text":
                if not isinstance(event.get("text"), str):
                    raise ProviderError("speech")
                parts.append(event["text"])
    except (ValueError, UnicodeError):
        raise ProviderError("speech") from None
    transcript = " ".join(parts).strip()
    if not transcript or len(transcript) > 12000:
        raise ProviderError("speech")
    return transcript


def wav_duration(raw):
    try:
        with wave.open(io.BytesIO(raw), "rb") as source:
            duration = source.getnframes() / source.getframerate()
            if (source.getcomptype() != "NONE" or source.getnchannels() != 1
                    or source.getsampwidth() != 2 or source.getframerate() != 24000):
                raise ProviderError("media")
            expected = source.getnframes() * source.getnchannels() * source.getsampwidth()
            if len(source.readframes(source.getnframes())) != expected:
                raise ProviderError("media")
    except (wave.Error, EOFError, OSError, ZeroDivisionError):
        raise ProviderError("media") from None
    if not 0 < duration <= MAX_AUDIO_SECONDS:
        raise ProviderError("media_limit")
    return duration


class ProviderClient:
    def __init__(self, deadline):
        self.deadline = deadline
        try:
            self.keys = load_keys(ROOT / ".env")
        except ProbeError:
            raise ProviderError("configuration") from None
        if not self.keys["gemini"]:
            raise ProviderError("configuration")

    def google(self, method, path, payload=None, raw_response=False):
        raw = request("gemini", self.keys["gemini"], path,
                      json.dumps(payload, separators=(",", ":")).encode("utf-8") if payload is not None else b"",
                      "application/json", self.deadline, 65536 if raw_response else 524288, method=method)
        if raw_response:
            return raw
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeError, RecursionError):
            raise ProviderError("provider_response", {"reason": "invalid_json_response"}) from None
        if not isinstance(value, dict):
            raise ProviderError("provider_response", {"reason": "unexpected_response_shape"})
        return value

    def interaction(self, payload):
        return self.google("POST", "/v1beta/interactions", payload)

    def transcribe(self, wav):
        if not self.keys["gradium"]:
            raise ProviderError("configuration")
        wav_duration(wav)
        path = STT_PATHS["runtime_context"]
        raw = request("gradium", self.keys["gradium"], path, wav, "audio/wav", self.deadline, 131072)
        return parse_transcript(raw)
