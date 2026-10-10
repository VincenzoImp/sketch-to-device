"""Isolated managed protocol tests; no credentials or provider calls."""

import base64
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend import program_agent as p


TOOLS = [{"type": "function", "name": name, "parameters": {
    "type": "object", "properties": {}, "additionalProperties": False}}
    for name in sorted(p.TOOL_NAMES)]
SELECTION = {"receipt_id": "receipt_one", "candidate_id": "candidate_one", "sha256": "a" * 64}


def response(status="requires_action", identity="first", calls=(), environment="env"):
    return {"id": identity, "agent": p.AGENT, "status": status,
            "environment_id": environment, "steps": list(calls)}


def call(identity="call_one", name="run_app", arguments=None):
    return {"type": "function_call", "id": identity, "name": name,
            "arguments": {} if arguments is None else arguments}


def result(text="tested", error=False, selection=None, image=False):
    content = [{"type": "text", "text": text}]
    if image:
        content.append({"type": "image", "mime_type": "image/png",
                        "data": base64.b64encode(b"\x89PNG\r\n\x1a\nsynthetic_protocol_only").decode()})
    return p.ToolResult(content, error, selection)


class Client:
    deadline = 0

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
        if isinstance(self.cancellation, Exception):
            raise self.cancellation
        return self.cancellation or {"id": path.rsplit("/", 1)[-1].removesuffix(":cancel"), "status": "cancelled"}


class ProgramAgentChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.job = Path(self.temporary.name) / "job"
        self.dispatched = []

    def run_agent(self, client, broker=None, clock=None, **changes):
        def execute(name, arguments, identity, deadline):
            self.dispatched.append((name, arguments, identity, deadline))
            return result(selection=SELECTION if name == "submit_app" else None)
        return p.run_program_agent([{"type": "text", "text": "PRIVATE_REQUEST"}],
            job_dir=self.job, tool_definitions=TOOLS, execute_tool=broker or execute,
            client=client, _clock=clock or (lambda: 1), _sleep=lambda _: None, **changes)

    def journal(self):
        return json.loads((self.job / "agent-state.json").read_text())

    def assert_fails(self, client, code="tool_protocol", **options):
        with self.assertRaises(p.ProviderError) as caught:
            self.run_agent(client, **options)
        self.assertEqual(caught.exception.code, code)
        self.assertNotIn("PRIVATE", str(caught.exception))

    def test_real_callback_results_images_and_same_environment_correlate(self):
        auto = [call("auto", "read_file"), {"type": "function_result", "call_id": "auto"},
                {"type": "google_search_result", "result": "public reference"}]
        client = Client([response(calls=auto + [call("asset", "prepare_uploaded_asset"), call("run")]),
                         response(identity="second", calls=[call("submit", "submit_app")])])
        def broker(name, arguments, identity, deadline):
            self.assertEqual(self.journal()["calls"][identity]["status"], "pending")
            return result(image=name == "run_app", selection=SELECTION if name == "submit_app" else None)
        self.assertEqual(self.run_agent(client, broker=broker), SELECTION)
        self.assertEqual(len(client.sent), 2)
        first, continuation = client.sent
        self.assertEqual([item["type"] for item in first["tools"][:3]], list(p.BUILTINS))
        self.assertEqual(continuation["previous_interaction_id"], "first")
        self.assertEqual(continuation["environment"], "env")
        self.assertEqual([item["call_id"] for item in continuation["input"]], ["asset", "run"])
        self.assertEqual(continuation["input"][1]["result"][1]["type"], "image")
        self.assertEqual(self.journal()["selection"], SELECTION)
        self.assertEqual(self.journal()["result"], "selected")
        self.assertEqual(client.cancelled, [("/v1beta/interactions/second:cancel", 10)])
        self.assertEqual(self.journal()["cancellation"], "confirmed")

    def test_only_submit_callback_can_select_not_provider_prose(self):
        self.assert_fails(Client([response("completed", calls=[{
            "type": "model_output", "content": [{"type": "text", "text": json.dumps(SELECTION)}]}])]))
        self.assertEqual(self.dispatched, [])
        self.assertNotIn("model_output", (self.job / "agent-last-response.json").read_text())

    def test_selection_from_run_or_error_is_rejected(self):
        for name, error in [("run_app", False), ("submit_app", True)]:
            self.job = Path(self.temporary.name) / name
            self.assert_fails(Client([response(calls=[call(name=name)])]),
                              broker=lambda *args: result(error=error, selection=SELECTION))

    def test_selected_result_survives_unconfirmed_cleanup_without_publication(self):
        client = Client([response(calls=[call(name="submit_app")])],
                        cancellation=p.ProviderError("provider_transport"))
        self.assertEqual(self.run_agent(client), SELECTION)
        self.assertEqual(self.journal()["cancellation"], "unconfirmed")
        self.assertTrue(self.journal()["remote_job_may_continue"])
        self.assertEqual(len(client.sent), 1)

    def test_completed_without_selection_and_incomplete_never_succeed(self):
        for state in ("completed", "incomplete", "failed", "cancelled"):
            self.job = Path(self.temporary.name) / state
            client = Client([response(state)])
            self.assert_fails(client)
            self.assertEqual(client.cancelled, [])

    def test_unknown_tool_bad_arguments_duplicate_ids_fail_before_any_callback(self):
        bad_calls = [[call(name="shell")], [call(arguments="PRIVATE_SOURCE")], [call(), call()],
                     [call(), call("bad", "shell")], [call(), call("submit", "submit_app")]]
        for index, calls in enumerate(bad_calls):
            self.job = Path(self.temporary.name) / str(index)
            self.assert_fails(Client([response(calls=calls)]))
        self.assertEqual(self.dispatched, [])

    def test_duplicate_cross_turn_id_never_dispatches_twice(self):
        client = Client([response(calls=[call()]), response(identity="second", calls=[call()])])
        self.assert_fails(client, "generation_stalled")
        self.assertEqual(len(self.dispatched), 1)

    def test_same_call_id_changed_arguments_is_protocol_failure(self):
        client = Client([response(calls=[call()]),
                         response(identity="second", calls=[call(arguments={"source": "changed"})])])
        self.assert_fails(client)
        self.assertEqual(len(self.dispatched), 1)

    def test_repair_can_progress_beyond_three_rounds_then_select(self):
        client = Client([response(identity="turn" + str(n), calls=[call("call" + str(n), arguments={"source": str(n)})])
                         for n in range(5)] + [response(identity="last", calls=[call("select", "submit_app")])])
        def broker(name, *_):
            return result("syntax failure", True) if name == "run_app" else result(selection=SELECTION)
        self.assertEqual(self.run_agent(client, broker=broker), SELECTION)
        self.assertEqual(len(client.sent), 6)
        self.assertTrue(client.sent[1]["input"][0]["is_error"])

    def test_identical_failed_request_twice_stalls(self):
        client = Client([response(calls=[call("one")]), response(identity="second", calls=[call("two")])])
        self.assert_fails(client, "generation_stalled", broker=lambda *args: result("same error", True))
        self.assertEqual(len(client.sent), 2)

    def test_late_callback_preserves_handle_and_bounded_cleanup(self):
        now = [1]
        def broker(*_):
            now[0] = 592
            return result()
        client = Client([response(calls=[call()])])
        self.assert_fails(client, "deadline", broker=broker, clock=lambda: now[0])
        self.assertEqual(client.cancelled, [("/v1beta/interactions/first:cancel", 601)])
        self.assertEqual(len(client.sent), 1)

    def test_late_submission_retains_receipt_but_cannot_return_selection(self):
        now = [1]
        def broker(*_):
            now[0] = 602
            return result(selection=SELECTION)
        client = Client([response(calls=[call(name="submit_app")])])
        self.assert_fails(client, "deadline", broker=broker, clock=lambda: now[0])
        self.assertEqual(self.journal()["result"], "failed")
        self.assertEqual(self.journal()["selection"], SELECTION)
        self.assertEqual(self.journal()["calls"]["call_one"]["status"], "returned")
        self.assertEqual(self.journal()["cancellation"], "unconfirmed")
        self.assertEqual(client.cancelled, [])
        self.assertEqual(len(client.sent), 1)

    def test_interrupt_is_journaled_and_rethrown_after_cleanup(self):
        def broker(*_):
            raise KeyboardInterrupt()
        client = Client([response(calls=[call()])])
        with self.assertRaises(KeyboardInterrupt):
            self.run_agent(client, broker=broker)
        self.assertEqual(self.journal()["result"], "interrupted")
        self.assertEqual(self.journal()["cancellation"], "confirmed")
        self.assertEqual(client.cancelled, [("/v1beta/interactions/first:cancel", 10)])

    def test_bad_poll_identity_cancels_requested_handle(self):
        client = Client([response("in_progress")], [response(identity="unexpected", calls=[call()])])
        self.assert_fails(client)
        self.assertEqual(client.cancelled[0], ("/v1beta/interactions/first:cancel", 10))

    def test_lost_continuation_retains_handle_and_uncertainty(self):
        client = Client([response(calls=[call()]), p.ProviderError("provider_transport")])
        self.assert_fails(client, "provider_transport")
        self.assertEqual(self.journal()["interaction_id"], "first")
        self.assertTrue(self.journal()["submission_unresolved"])
        self.assertEqual(self.journal()["cancellation"], "unconfirmed")

    def test_malformed_new_status_cancels_new_known_id(self):
        client = Client([response(calls=[call()]), response("invalid", "new")])
        self.assert_fails(client)
        self.assertEqual(client.cancelled[0][0], "/v1beta/interactions/new:cancel")

    def test_changed_environment_fails_before_next_tool(self):
        client = Client([response(calls=[call()]),
                         response(identity="second", environment="other", calls=[call("two")])])
        self.assert_fails(client)
        self.assertEqual(len(self.dispatched), 1)

    def test_existing_journal_never_creates_second_job(self):
        self.job.mkdir()
        (self.job / "agent-state.json").write_text("PRIVATE_OLD_STATE")
        client = Client([])
        self.assert_fails(client, "generation")
        self.assertEqual(client.sent, [])
        self.assertEqual((self.job / "agent-state.json").read_text(), "PRIVATE_OLD_STATE")

    def test_private_journal_and_result_files_have_no_public_raw_exception(self):
        client = Client([response(calls=[call()])])
        def broker(*_):
            raise RuntimeError("PRIVATE_SECRET")
        self.assert_fails(client, "generation", broker=broker)
        for path in self.job.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertNotIn("PRIVATE_SECRET", path.read_text())

    def test_write_failure_before_create_prevents_provider_request(self):
        client = Client([])
        with patch.object(p, "_write", side_effect=p.ProviderError("generation")):
            self.assert_fails(client, "generation")
        self.assertEqual(client.sent, [])

    def test_sdk_mounts_canonical_bytes_hashes_and_only_own_startup(self):
        sources = p.sdk_sources()
        by_target = {item["target"]: item["content"] for item in sources}
        self.assertEqual(len(sources), len(by_target))
        self.assertEqual(by_target["/workspace/program-sdk/contracts/program-profile.json"],
                         (p.ROOT / "contracts/program-profile.json").read_text())
        self.assertEqual(by_target[".agents/AGENTS.md"],
                         (p.ROOT / "agent-sdk/program-v1/.agents/AGENTS.md").read_text())
        self.assertNotEqual(by_target[".agents/AGENTS.md"], (p.ROOT / "AGENTS.md").read_text())
        manifest = json.loads(by_target["/workspace/program-sdk/manifest.json"])
        self.assertEqual(manifest["builtin_tools"], list(p.BUILTINS))
        for entry in manifest["files"]:
            raw = by_target[entry["target"]].encode()
            self.assertEqual(entry["bytes"], len(raw))
            self.assertEqual(entry["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertLess(sum(len(item["content"].encode()) for item in sources), 32768)

    def test_invalid_profile_and_tool_definitions_fail_before_private_or_network_work(self):
        client = Client([])
        self.assert_fails(client, "input", model="invented")
        self.assertFalse(self.job.exists())
        with self.assertRaises(p.ProviderError):
            p._definitions(TOOLS + TOOLS[:1])
        self.assertEqual(client.sent, [])


if __name__ == "__main__":
    unittest.main()
