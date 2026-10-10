# Backend implementation

[server.py](server.py) serves the [mobile companion](../companion/README.md), receives private media uploads, starts one generation worker, and exposes authenticated desired-package/download/ACK routes. Run `python3 -B -m backend.server` from the repository root. It binds localhost port 8787 by default and creates private configuration/data under `private/service/`. The HTTPS launcher verifies a working public origin before opening its private QR setup page. One actual Android voice request has reached a generated, acknowledged and physically exercised app; its title was mistranscribed. Visual input and repeated full runs remain open acceptance work.

The session bearer token and device bearer token have separate roles. Provider keys never reach either client. The demo has one preprovisioned session/device; public pairing claims and a multi-user account system are outside this version. Tokens are generated into the private configuration, not printed in logs. A known app is published only after trusted validation; the UI reports activation only when an exact current ACK matches. A lost generation response can be retried with the same frozen request ID; the companion resumes accepted jobs after reload. In-progress generation is failed explicitly after server restart, while already-published packages remain deliverable.

`tests/test_service.py` exercises actual HTTP handler parsing/dispatch using in-memory sockets and real temporary SQLite stores. This verifies authentication boundaries, routes, exact package bytes and acknowledgments, idempotency, restart and failed job-start recovery. It does not establish TCP/TLS reachability, browser recording, provider generation or physical activation.

## Managed generation

[generator.py](generator.py) exposes `generate_app(prompt, media, progress) -> bytes`. Gradium transcribes recording audio; Gemini receives the frozen concept and supported images, then builds a source-version-1 AppSpec in its remote environment. The environment retains the full canonical schema, capabilities and trusted runtime with network access disabled. Its first read is a derived, readable guide of approximately 5.6 kB with one labeled syntax example. The model then writes request-specific JSON using a quoted heredoc and runs the mounted trusted checker. An example is never mounted as the output artifact.

Each interaction has a best-effort 50,000-token limit. The whole job has a 180-second deadline, including a ten-second cancellation reserve, and at most two repair turns. Downloaded bytes must pass independent local validation and runtime behavior checks, and match a paired remote checker execution hash. Arbitrary generated code never runs on the Mac or device. The deployment store subsequently assigns and validates the served publication version.

Two text generations passed earlier. Three Android audio attempts reached nonempty transcription but failed generation; three diagnostic replays exhausted their respective 32,768/50,000-token budgets. The third replay completed both prescribed commands and produced a trusted-check hash, but its terminal `incomplete` state prevented artifact retrieval. The accepted recovery correction passes 29 focused tests: a terminal incomplete run may yield an app only when a paired successful checker result exists and the actual downloaded bytes pass the same hash and host checks. An invalid incomplete artifact fails without continuation or repair; the provider status remains incomplete in the private trace. Two subsequent replays completed normally and downloaded host-valid apps, without exercising that recovery branch. Their incorrect transcripts produced apps that failed the intended tap-game behavior. [Managed generation evidence](../docs/research/managed-probe.md) records these distinct results; generation success alone does not establish intent fidelity or physical installation.

[The speech comparison probe](../scripts/probe_speech.py) is inert unless both `--live --last-failed` are supplied. It compares the same frozen recording with baseline English transcription and a fixed, modest runtime-vocabulary profile, storing transcripts only in private files. It makes no Gemini request, changes no production transcription setting and installs nothing; keyword detection is not an accuracy score.

The live same-recording comparison subsequently recognized the tap-game phrase and requested title with the runtime-vocabulary profile, while preserving the requested duration. The production adapter selects this profile and the coordinated service restart has completed. In the subsequent real Android request, transcription still changed **Rocket Tap** to **Rocket Tata** and did not activate the narrow tap-game/duration detector. Production therefore used generic checks. Independent checks of the exact published package afterward passed the intended 15-second tap scenario and additional deadline/restart tests.

That request produced `rocket_tata`, sequence 6, version 1; the board acknowledged the exact 1,307-byte served package. The user confirmed Start, scoring, final score after 15 seconds, Play again resetting the round, phone installation confirmation and restoration after an ordinary reboot. Source and served hashes, provider status and archived evidence are recorded in [managed generation evidence](../docs/research/managed-probe.md). These establish one generated physical flow with a title mismatch, not full transcript accuracy, visual understanding, three repeated successful runs or interrupted-install recovery.

## Deployment store

[deployments.py](deployments.py) implements a dependency-free SQLite slice of the [deployment contract](../docs/04-contracts.md). It stores frozen install intents, trusted package bytes/manifests, desired and last-acknowledged active identities, and historical ACK receipts. This is not an HTTP server, provider adapter, firmware updater, or authenticated end-to-end system.

The [trusted AppSpec parser](../runtime/validation.py) is used directly. Publication assigns the backend version, serializes the final package, and validates those exact bytes before committing them. It records the original artifact SHA-256 separately from the served-byte SHA-256. No report supplied by a model is accepted as validation evidence. The implemented [generation worker](generator.py) checks managed tool execution and independently runs trusted host behavior checks before publication.

## Interface

Create `DeploymentStore(database_path)` in a context manager, or call `close()` when finished. Use one instance/connection per worker thread or process. Python 3.9+ and its standard library are sufficient. Real databases contain private request snapshots and must stay outside public exports; the tests use temporary directories.

| Method | Responsibility |
| --- | --- |
| `bind_device(session_id, device_id)` | Trusted local provisioning/rebinding only. Creates the session if needed; rebinding revokes the previous intent and queued desired package while retaining the last accepted active identity |
| `accept_intent(session_id, device_id, idempotency_key, request, *, require_idle=False)` | Freeze 1–65,536 exact request bytes and the bound target. The same key and bytes/target return the same intent; any change conflicts. A new intent gets the next device sequence and immediately clears older desired work. Trusted fixture publication uses the optional atomic idle guard to preserve an accepted generation |
| `get_intent(session_id, intent_id)` | Read that session's historical intent status |
| `fail_intent(session_id, intent_id, error_code)` | Mark an accepted generation as failed without changing the known active package |
| `publish(session_id, intent_id, artifact)` | Validate and transactionally publish artifact bytes for the current bound intent. Repeating with the same original bytes is idempotent; different bytes conflict |
| `desired_for_device(authenticated_device_id)` | Return the current `{deployment_id, sequence, manifest}` or `None` |
| `package_for_device(authenticated_device_id, deployment_id)` | Return only that device's currently desired bytes after integrity/identity revalidation |
| `active_for_session(session_id, device_id)` | Return the last active identity accepted for that bound device, or `None`; this is not a live device-health observation |
| `record_ack(authenticated_device_id, ack)` | Require exact device/deployment/sequence/app/version/hash identity. Return receipt/idempotency information and whether the current desired deployment is known active |
| `ack_history(session_id, intent_id)` | Read historical ACK statuses for that session's intent; historical receipt is not current install success |

The caller must supply identities established by real authentication. Passing a client-controlled `device_id` or `session_id` as an authenticated identity would be unsafe. The store verifies resource ownership/binding; [server.py](server.py) verifies separate session/device bearer tokens before calling it. `bind_device` is a trusted setup function and is not exposed as a public pairing claim. Public pairing codes and multiple accounts remain unimplemented.

Request snapshots are opaque bytes. The HTTP service freezes the prompt and verified attachment metadata consistently before accepting the intent. Whitespace changes count as changed input for idempotency. The store never executes or interprets request content. While its single generation worker is busy, the service rejects another request with `409 generation_busy`; it does not queue or cancel jobs. An identical accepted request ID still returns its original job.

`publish` returns the contract envelope. Versions increase per session and app ID; device sequences increase across all intents, including trusted rebindings. Download paths are produced locally from the validated app ID/version. Manifest identity, size and hash are checked against the persisted body before download or ACK accounting. A changed in-memory result dictionary cannot alter the stored bytes.

## Transaction and acknowledgment behavior

SQLite `BEGIN IMMEDIATE` serializes mutations and the read snapshots used for package/ACK decisions. The package body, manifest fields, published intent state and desired pointer commit in one database transaction; there is no separately written package file. `synchronous=FULL` is enabled. Tests prove logical rollback and reopening behavior, not physical disk power-loss guarantees.

Accepting a newer intent immediately revokes an older queued desired deployment even while the new generation is still running. The old active package remains available as the last accepted active identity. A stale worker cannot publish over the newer intent; a late ACK is stored historically without completing the new intent or moving its desired/active pointers.

ACK stages progress monotonically through downloading, validating, activating and active. Duplicate active ACKs do not duplicate receipt records or reinstall anything. An installation failure before active clears desired work and preserves the previous active identity; retry requires a new intent. Active and failed are terminal installation outcomes, so out-of-order later installation-stage messages are only historical receipts. Runtime health/rollback reports after a completed installation need a separate future contract; this store does not turn them into invented physical observations.

Store serialization cannot control a device that already downloaded a superseded package. The firmware must recheck desired deployment identity before committing activation, as specified in the shared contract. Store tests alone do not exercise a device; actual installation evidence is recorded separately above.

## Practical checks

From the repository root:

```sh
python3 -B -m unittest discover -s tests -p test_deployments.py -v
```

The current store suite passed **22 tests** using real temporary SQLite databases. They cover reopen persistence, exact request and publication idempotency, backend version assignment and byte hashes, session/device ownership including missing or malformed identities, rebinding, revocation of queued work, historical/duplicate ACKs, invalid package preservation, corrupt body/hash/size/identity rejection, SQL-trigger failure rollback, and concurrent intent/publication operations using separate connections.

All package inputs in these tests are explicitly hand-authored [acceptance fixtures](../contracts/README.md). No provider, Android, network, firmware, physical activation, or GPIO behavior is claimed. Independent review and integration-gate status belong to [the work ledger](../docs/12-work-ledger.md).

For device bring-up, [the local fixture installer](../scripts/install_fixture.py) publishes a clearly labeled known package and reads the exact real device ACK. Its atomic idle guard preserves an in-flight generation request. It does not call a provider or establish the phone flow. Use `--install tap-sprint` or `--install focus-timer` only during bring-up; `--status` inspects the most recent fixture deployment.
