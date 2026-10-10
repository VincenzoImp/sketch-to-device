"""Isolated protocol checks; these do not establish live provider integration."""

import base64
import copy
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

from scripts import probe_programmable_agent as p


def response(status, identity="first", steps=None, environment="environment"):
    return {"id": identity, "agent": p.AGENT, "environment_id": environment,
            "status": status, "steps": steps or []}


def call(**changes):
    value = {"type": "function_call", "id": "call_one", "name": p.TOOL_NAME,
             "arguments": dict(p.ARGUMENTS)}
    value.update(changes)
    return value


def final(color="blue"):
    observation = {"visible_title": "Hello World", "button_text": "Change color", "button_color": color}
    return response("completed", "second", [{"type": "model_output", "content": [
        {"type": "text", "text": json.dumps(observation)}]}])


class Client:
    deadline = 590

    def __init__(self, creates, polls=(), cancellation=None):
        self.creates, self.polls = list(creates), list(polls)
        self.sent, self.gets, self.cancelled = [], [], []
        self.cancellation = cancellation

    def interaction(self, payload):
        self.sent.append(copy.deepcopy(payload))
        value = self.creates.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    def google(self, method, path, payload=None):
        if method == "GET":
            self.gets.append(path)
            return self.polls.pop(0)
        self.cancelled.append((path, self.deadline))
        return self.cancellation or {"id": path.split("/")[-2], "status": "cancelled"}


class ProtocolChecks(unittest.TestCase):
    def run_probe(self, client, checker=None, clock=None, journal=None):
        calls = []
        def proof(deadline):
            calls.append(deadline)
            return {"scope": "fixed_builtin_host_ui_proof_only"}, b"synthetic_test_png", "blue"
        result, trace = p.probe(client, checker or proof, 590, sleep=lambda n: None,
                                clock=clock or (lambda: 1), journal=journal)
        return result, trace, calls

    def test_correlated_image_result_and_matching_visual_observation(self):
        client = Client([response("requires_action", steps=[call()]), final()])
        saved = []
        result, trace, calls = self.run_probe(client, journal=lambda v: saved.append(copy.deepcopy(v)))
        self.assertEqual(result["result"], "managed_custom_tool_roundtrip_passed")
        self.assertEqual(len(calls), 1)
        self.assertTrue(result["image_observation_matched"])
        payload = client.sent[1]
        self.assertEqual(payload["previous_interaction_id"], "first")
        self.assertEqual(payload["environment"], "environment")
        content = payload["input"][0]
        self.assertEqual(content["call_id"], "call_one")
        self.assertEqual(content["name"], p.TOOL_NAME)
        self.assertEqual([v["type"] for v in content["result"]], ["text", "image"])
        self.assertEqual(base64.b64decode(content["result"][1]["data"]), b"synthetic_test_png")
        self.assertNotIn("blue", content["result"][0]["text"])
        self.assertTrue(any(v["resume_state"]["last_known_interaction_id"] == "first"
                            and v["resume_state"]["submission_unresolved"] for v in saved))
        self.assertEqual(client.cancelled, [])

    def test_wrong_image_observation_is_failure_despite_completed_status(self):
        client = Client([response("requires_action", steps=[call()]), final("pink")])
        result, _, _ = self.run_probe(client)
        self.assertEqual(result["error_code"], "image_observation_failed")
        self.assertTrue(result["continuation_completed"])
        self.assertFalse(result["image_observation_matched"])

    def test_checker_expiring_deadline_cancels_known_first_interaction(self):
        now = [1]
        def checker(deadline):
            now[0] = 591
            return {}, b"image", "blue"
        client = Client([response("requires_action", steps=[call()])])
        result, _, _ = self.run_probe(client, checker=checker, clock=lambda: now[0])
        self.assertEqual(result["error_code"], "deadline")
        self.assertEqual(len(client.sent), 1)
        self.assertEqual(client.cancelled, [("/v1beta/interactions/first/cancel", 600)])
        self.assertEqual(result["cancellation"], "confirmed")

    def test_poll_identity_mismatch_retains_requested_cancellation_id(self):
        client = Client([response("in_progress")], [response("requires_action", "unexpected", [call()])])
        result, _, calls = self.run_probe(client)
        self.assertEqual(result["error_code"], "identity_changed")
        self.assertEqual(calls, [])
        self.assertEqual(client.cancelled, [("/v1beta/interactions/first/cancel", 10)])

    def test_early_failure_cleanup_has_nine_second_budget(self):
        client = Client([response("requires_action", steps=[call(name="shell")])])
        result, _, calls = self.run_probe(client)
        self.assertEqual(calls, [])
        self.assertEqual(client.cancelled[0][1], 10)
        self.assertEqual(result["cancellation"], "confirmed")

    def test_lost_continuation_response_preserves_identity_and_unknown_remote_state(self):
        client = Client([response("requires_action", steps=[call()]), p.ProviderError("provider_transport")])
        result, trace, _ = self.run_probe(client)
        self.assertEqual(client.cancelled[0][0], "/v1beta/interactions/first/cancel")
        self.assertEqual(result["cancellation"], "unconfirmed")
        self.assertTrue(result["remote_job_may_continue"])
        self.assertEqual(trace["resume_state"]["last_known_interaction_id"], "first")
        self.assertTrue(trace["resume_state"]["submission_unresolved"])

    def test_unknown_state_after_continuation_cancels_new_known_id(self):
        client = Client([response("requires_action", steps=[call()]), response("unknown", "second")])
        result, _, _ = self.run_probe(client)
        self.assertEqual(result["error_code"], "invalid_state")
        self.assertEqual(client.cancelled, [("/v1beta/interactions/second/cancel", 10)])

    def test_environment_mismatch_is_not_success(self):
        client = Client([response("requires_action", steps=[call()]),
                         response("requires_action", "second", environment="different")])
        result, _, _ = self.run_probe(client)
        self.assertEqual(result["error_code"], "identity_changed")
        self.assertFalse(result["continuation_completed"])

    def test_unmatched_cancel_response_cannot_confirm_cancellation(self):
        client = Client([response("requires_action", steps=[call(name="shell")])],
                        cancellation={"id": "other", "status": "cancelled"})
        result, _, _ = self.run_probe(client)
        self.assertEqual(result["cancellation"], "unconfirmed")

    def test_unknown_arguments_and_malformed_ids_never_reach_checker(self):
        for item in [call(arguments={**p.ARGUMENTS, "command": "PRIVATE_SECRET"}),
                     call(arguments=json.dumps(p.ARGUMENTS)), call(id=[]), call(name="shell")]:
            with self.subTest(item=item):
                client = Client([response("requires_action", steps=[item])])
                result, _, calls = self.run_probe(client)
                self.assertEqual(calls, [])
                self.assertNotIn("PRIVATE_SECRET", json.dumps(result))
                self.assertEqual(result["result"], "failed")

    def test_completed_prose_is_not_execution_evidence(self):
        client = Client([response("completed")])
        result, _, calls = self.run_probe(client)
        self.assertEqual(result["error_code"], "missing_tool_call")
        self.assertEqual(calls, [])

    def test_automatic_filesystem_result_ignored_and_duplicate_pending_rejected(self):
        steps = [call(name="read_file", id="auto"), {"type": "function_result", "call_id": "auto"}, call()]
        self.assertEqual(p.pending_call(response("requires_action", steps=steps))["id"], "call_one")
        with self.assertRaises(p.Failure):
            p.pending_call(response("requires_action", steps=[call(), call(id="two")]))

    def test_default_inert_and_journal_failure_prevents_outbound(self):
        with patch.object(p, "ProviderClient", side_effect=AssertionError), \
             patch.object(p.ui, "status", side_effect=AssertionError), patch("builtins.print"):
            self.assertEqual(p.main([]), 0)
        client = Client([])
        def broken(_):
            raise OSError("PRIVATE_SECRET")
        result, _, _ = self.run_probe(client, journal=broken)
        self.assertEqual(client.sent, [])
        self.assertEqual(result["error_code"], "evidence_write_failed")
        self.assertNotIn("PRIVATE_SECRET", json.dumps(result))

    def test_png_encoding_preserves_exact_renderer_pixels(self):
        pixels = bytes((i % 251 for i in range(320 * 480 * 3)))
        png = p.ppm_png(b"P6\n320 480\n255\n" + pixels)
        offset, compressed, width = 8, b"", None
        while offset < len(png):
            size = struct.unpack(">I", png[offset:offset + 4])[0]
            kind, body = png[offset + 4:offset + 8], png[offset + 8:offset + 8 + size]
            self.assertEqual(struct.unpack(">I", png[offset + 8 + size:offset + 12 + size])[0],
                             zlib.crc32(kind + body))
            if kind == b"IHDR":
                self.assertEqual(struct.unpack(">IIBBBBB", body), (320, 480, 8, 2, 0, 0, 0))
            if kind == b"IDAT":
                compressed += body
            offset += 12 + size
        rows = zlib.decompress(compressed)
        self.assertEqual(b"".join(rows[y * 961 + 1:(y + 1) * 961] for y in range(480)), pixels)
        with self.assertRaises(p.Failure):
            p.ppm_png(b"PRIVATE_SECRET")

    def test_private_journal_is_atomic_restrictive_and_refuses_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder).resolve() / "trace.json"
            p.atomic_json(path, {"id": "known"})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(path.read_text()), {"id": "known"})
            other = path.with_name("link.json")
            other.symlink_to(path)
            with self.assertRaises(p.Failure):
                p.atomic_json(other, {})

    def test_checker_does_not_repeat_preflight_after_deadline(self):
        with patch.object(p.ui, "status", side_effect=AssertionError), \
             patch.object(p.time, "monotonic", return_value=600):
            with self.assertRaises(p.ProviderError) as caught:
                p.host_proof(590)
            self.assertEqual(caught.exception.code, "deadline")


if __name__ == "__main__":
    unittest.main()
