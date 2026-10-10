# Managed-agent execution and artifact probe

Research and tooling prepared on **10 October 2026**. The latest milestone is a real Android voice request reaching a generated app, exact physical acknowledgment, confirmed game controls and ordinary reboot restoration. The requested title was mistranscribed; strict 15-second behavior passed independent checks after production's generic validation. See the final section for exact hashes and limits. Earlier probes, failed replays and successful command-line generations remain historical evidence. Incomplete-artifact recovery is reviewed but has not been exercised successfully by a live incomplete run. [Provider evidence](provider-probe.md) and the [work ledger](../12-work-ledger.md) record the wider context.

## Tiny-probe command: historical capability check

```sh
python3 -B /Users/vincenzo/hackathon/scripts/probe_managed_agent.py --live --max-total-tokens 16384
```

This requires only Python 3.9+ and the existing private project `.env`. Process environment values take precedence, as in the provider probe. Keys stay in HTTPS headers. The script imports its sibling `probe_providers.py`; keep both files together. It does not install an SDK, read project source/media, run a local shell, or upload repository contents.

`--live` creates one real managed job and may consume provider quota. Without that flag, the script sends no requests and does not read credentials. `--self-test` uses only isolated fixtures. Default local job budget is 180 seconds, including a 10-second cancellation reserve; `--job-timeout` accepts 30–300 seconds. HTTP exchanges are individually bounded at 30 seconds, including slow response headers, and use the remaining job budget when shorter. `--max-total-tokens` permits 4096 (unchanged default) or an explicit 16384; there is no automatic escalation or continuation.

## Documented REST contract

All calls use `https://generativelanguage.googleapis.com` with certificate verification and `x-goog-api-key`. No redirects, failed-request retries, model substitutions, proxy routes or alternate services are used. Each request opens one verified connection; a failed preflight stops its dependent request.

| Operation | Method and path | Project use |
|---|---|---|
| Create | `POST /v1beta/interactions` | Agent `antigravity-preview-09-2026`, `background: true`, `store: true` |
| Poll | `GET /v1beta/interactions/{id}` | Poll queued/in-progress states every two seconds; stop on other states |
| List | `GET /v1beta/environments/{id}/files?recursive=true` | Find exactly one expected result file in returned metadata |
| Download | `GET /v1beta/environments/{id}/files/{path}?alt=media` | Retrieve the actual bytes of that file |
| Cancel | `POST /v1beta/interactions/{id}/cancel` | One bounded cancellation attempt if a known job remains active after failure/deadline |

The current Antigravity guide documents the September agent identifier, a configurable `max_total_tokens`, and restricting tools through the `tools` array. The probe supplies only `code_execution` and the explicitly selected token budget. Filesystem tools accompany the environment. The budget includes input, output and thinking, excludes cached tokens, and reaching it returns `incomplete`; enforcement is best effort between steps. This makes the initial 4096-token cap a plausible cause, not an established diagnosis. [Antigravity guide](https://ai.google.dev/gemini-api/docs/antigravity-agent)

Background execution requires stored interactions. The current background guide and OpenAPI agree on `/interactions/{id}/cancel`; an older colon-style cancellation snippet elsewhere is not used. The generic reference still lists an older Antigravity enum; the current dedicated guide supplies the selected September identifier. These source inconsistencies remain distinct from actual account access. [Background execution](https://ai.google.dev/gemini-api/docs/background-execution), [official OpenAPI](https://ai.google.dev/static/api/interactions.openapi.json)

The environment is a fresh remote sandbox with `network: "disabled"` and one `inline` source at `/workspace/provider_probe.py`. Inline sources contain their text in `content`. Files metadata provides paths relative to the environment root; the probe accepts the returned result path only as `provider_probe_result.txt` or `workspace/provider_probe_result.txt`. It downloads that selected path once, without trying alternate endpoints. The deprecated snapshot endpoint and tar extraction are unused. [Environment sources, network and Files API](https://ai.google.dev/gemini-api/docs/agent-environment)

## Required evidence

The fixed, public script writes the 26-byte ASCII artifact `MANAGED_AGENT_ARTIFACT_V1` followed by a newline, checks its bytes, and prints `PROBE_EXECUTED` followed by the SHA-256 of those bytes. The input asks the agent to execute the mounted script using Python 3. The output artifact itself is not mounted or locally substituted.

A passing report requires all of the following:

1. A completed interaction with a consistent interaction ID.
2. A structured `code_execution_call` referring to the mounted script, paired by ID with a non-error `code_execution_result` containing the expected execution marker.
3. Exactly one expected result file selected from Environment Files metadata.
4. Downloaded bytes exactly equal to the expected artifact, with the SHA-256 calculated locally from the download.

The documented execution steps carry `arguments.code`, call `id`, result `call_id`, string `result` and optional `is_error`. Final model prose and filesystem call counts cannot satisfy the execution check. Unknown trace shapes remain an evidence gap; they are not silently accepted. [Interactions step schema](https://ai.google.dev/api/interactions-api)

Output contains fixed diagnostic codes, permitted states, step counts, booleans, byte counts and hashes. Keys, raw provider errors, trace text, prompts, interaction/environment identifiers and downloaded content are not printed. JSON responses are capped at 256 KiB and the artifact download at 4 KiB. Google failures reuse the provider probe's allowlisted diagnostic classifier.

The diagnostic revision also retains six documented integer usage totals and safe execution counts before rejecting an incomplete interaction. Booleans, strings, negative/oversized values and unknown fields are omitted. The current Interactions reference/OpenAPI documents no `incomplete_details` reason field, so `incomplete_reason: unclassified` is a local diagnostic label. Unknown reason text is never printed or treated as a confirmed budget failure.

`passed` establishes only this tiny managed-execution/download capability. It does not prove app generation, repair, Gradium speech or installation on hardware. `execution_evidence_missing` can accompany a successful file download and still means the full probe failed. `incomplete`, `requires_action`, missing/mismatched files and unknown states cannot become success.

If a known active job fails or reaches the work deadline, the reserved time allows one cancellation request. Cancellation is confirmed only from the returned state. A lost creation response can leave no usable ID; the CLI then reports that the remote job may continue. The token cap remains in the original request. The local deadline is not a guarantee of remote cancellation. This diagnostic does not delete the resulting public sandbox or interaction.

## Verification status

`python3 -B scripts/probe_managed_agent.py --self-test` passed **10 synthetic tests** covering payload privacy, prose-only/unpaired/failed execution rejection, actual-download comparison in fixtures, hostile identifiers/paths, incomplete status, numeric usage redaction, explicit token budgets, deadline/cancellation, blocked DNS, slow headers and bounded/error-redacted responses. These results are unit-only. The no-flag invocation returned `live_not_requested` and zero requests without accessing credentials.

The initial tool passed independent review and five additional reviewer-authored negative checks. Its diagnostic revision also passed focused re-review, including malformed usage, incomplete-state reporting, and invalid-budget rejection before credential access. No live managed request was repeated from the unchanged restricted shell.

## Live observations

The user supplied normal-terminal output dated **10 October 2026 at 10:44:20 UTC**: network passed, three requests were sent, elapsed time was **18825 ms**, and the interaction reached `incomplete` during polling. The result was `interaction_not_completed`, `artifact_downloaded: false`, `cancellation: not_needed`, and `remote_job_may_continue: false`. The first version did not report usage or execution steps for incomplete jobs. Neither a completed command nor a retrievable artifact is established by this observation.

After review, the next check used the explicit 16384-token budget and unchanged 180-second deadline. It tested the budget hypothesis while collecting safe counters without establishing that the earlier job exhausted its cap. Incomplete jobs still fail and do not trigger artifact fetches, continuations or automatic repetition.

The user then supplied a successful **16384-token** run dated **10 October 2026 at 10:51:59 UTC**: `completed`, one paired code-execution call/result, six requests, and **20582 ms** elapsed. The downloaded artifact contained exactly **26 bytes** and matched SHA-256 `11d9a4df17198f4d2c2477dafb8492a38ff5b929c6f2b1d9bdb206a7da6bc636`. Reported usage was 9858 input, 128 output, 362 thinking, 3289 cached and 10348 total tokens. This proves the small managed execution/download path in the user's terminal. It does not establish the cause of the first incomplete run or prove app generation; no unchanged retry is needed.

The coordinator selected the proven managed path as the primary generation route: mount public trusted contracts/checks, generate and download an AppSpec, then independently validate it locally. Local Gemini tool calling remains a declared fallback. Preserve integration results in the [work ledger](../12-work-ledger.md) and [readiness register](../11-readiness.md). The current project documents record no verified managed-only event rule; any later fallback selection remains an explicit coordinator decision against [the event brief](../01-event.md) and [Gemini research](gemini.md).

## Production adapter

The implementation in [generator.py](../../backend/generator.py) and [providers.py](../../backend/providers.py) keeps the same managed execution/download route. Its interface is `generate_app(prompt, media, progress) -> bytes`: source-version-1 AppSpec bytes, independently checked before the deployment service assigns a publication version. Input snapshots are frozen before provider access. Credentials remain backend-only. The environment mounts only fixed public contract/runtime files and a trusted checker; its network is disabled.

The current adapter uses a best-effort **50,000-token budget per interaction**, at most two repair turns, and a **180-second local job deadline** including ten seconds reserved for cancellation. The original 32,768-token setting is historical. Each HTTP request has a whole-exchange deadline. Cancellation remains best effort if a create response is lost or a provider cannot be reached. A local deadline does not prove a remote job stopped.

The agent first reads a derived, readable authoring guide containing schema syntax, runtime limits, measured requirements and one explicitly labeled reference example. Current guides are approximately 5.6 kB, with 165 lines and a maximum line length of 109 characters; the generator enforces 7,500 bytes and 500 characters per line. The full canonical schema, capabilities, runtime and trusted checker remain mounted unchanged. The next command writes request-specific raw JSON through a quoted heredoc and runs the standalone trusted checker. No generated output is preseeded, and the reference example is not permission to substitute its title or duration for the request.

A downloaded app must satisfy local AppSpec validation and trusted runtime checks. The tap-game check tests start, scoring, exact expiry, ignored deadline taps, and restart. Other apps receive bounded control/timer exploration; this is not proof of arbitrary intent fidelity. A paired remote code-execution result must also contain the exact downloaded app hash. Prose alone cannot pass. Generated code never executes on the Mac or ESP32.

The agent accepts inline images directly. Audio goes to Gradium REST STT; native WebM/MP4 uses trusted FFmpeg conversion first. Video is represented by one midpoint frame plus speech, so this implementation does not inspect every frame or prove temporal visual understanding. Attachments are limited to three, 20 MiB total, and 30 seconds per recording. Browser WebM without duration metadata receives a bounded decode to measure its duration. [Agent image input](https://ai.google.dev/gemini-api/docs/antigravity-agent), [Gradium completed-file STT](https://docs.gradium.ai/guides/speech-to-text-rest)

At the original production-slice checkpoint, [generation tests](../../tests/test_generation.py) passed 17 isolated checks and the complete local suite passed 86 tests. Independent review accepted that slice for a text-only live smoke, including actual nonseekable-WebM conversion, PATH fallback and overlong-input rejection. These historical counts are superseded by the latest focused result below; offline checks never establish provider, phone or hardware integration.

Actual local conversion checks used FFmpeg/FFprobe 9.0.2 at `/opt/homebrew/bin` on 10 October. Synthetic one-second tones converted from WebM, MP3, Ogg, M4A and MOV to mono 16-bit 24 kHz PCM WAV with exactly one second of decoded audio. Nonseekable WebM exercised the missing-duration branch. Synthetic video produced a midpoint JPEG; a 31-second WebM was rejected with `media_limit`. The backend uses the known Homebrew path when these tools are absent from PATH. No synthetic tone was sent to Gradium; these checks prove conversion only.

| Actual synthetic source | SHA-256 | Observed result |
|---|---|---|
| One-second WebM | `86a29059832be41a451b1eeeac21443e4361f013ef81407c8cdcbcdd0472a831` | 48078-byte WAV, 1.0 seconds |
| 31-second WebM | `3ce8a0cf01116855b4ae8d5e136b7616cfe651a4cdfeb6ca49fea7859a4a4b33` | Rejected before transcription |
| Nonseekable audio WebM | `28e8813976d9c3035c8838a0e93f98b7f463ac086d19deabcf57e2ef3b5a7ecd` | 1.0-second WAV |
| Nonseekable video WebM | `9a3c616f39a2ebd17060267323637db27a24e6d0509ee05ac5df8d6de2c78dbd` | 1.0-second WAV, 2818-byte JPEG |
| MP3 | `023cf872d033b8e8a781ad3b03882c8ad6c9f3ad416ee1c69cec55b0de57b1be` | 1.0-second WAV |
| Ogg | `e987c55315f6bf275a8a9514630c56c2005c9f62b75c4d2387036ea425079b34` | 1.0-second WAV |
| M4A | `549d7c8f9cf5a7803722e7683bb0d04c2758d602a3730d22f238e9adc41ddf3d` | 1.0-second WAV |
| MOV | `78e3ba5b84e9b4b2793425099d7ce04675eff0e224fedc458a89eb30399b9fba` | 1.0-second WAV, 2815-byte JPEG |

The accepted real text-only smoke command from the repository is:

```sh
python3 -B -m backend.generator --live
```

It writes `artifacts/generated-app.json` only after generation and host validation. Without `--live` it reads no credentials and performs no calls. This smoke does not install an app or exercise Gradium; the final spoken Android path must do both.

## Historical production generation failure: diagnostic revision

At approximately **13:16 Europe/Zurich**, the coordinator reported three user-terminal production attempts through `scripts/generate_once.py --live`. Each reached the `generating` stage, then returned the generic `provider_response` error before local validation. No generated app was established. These observations did not include elapsed time, terminal interaction state, usage or the failed parsing phase, so the cause cannot yet be classified.

At this checkpoint, the payload used the same agent, remote inline environment, code-execution tool and background/store settings as the successful tiny probe. Its larger source/task and system instruction were differences, not demonstrated causes. No incomplete continuation or automatic budget increase was introduced. Later measured voice-budget failures and explicit corrections are recorded below.

The diagnostic revision exposed only fixed phases/reasons, known interaction states, six bounded integer usage totals, safe step counts, attempt number and elapsed milliseconds. Missing artifacts, malformed resource IDs, unexpected statuses, oversized bodies and incomplete interactions became distinguishable. It excluded prompts, raw messages, identifiers, file names, provider output and unknown reason fields; the CLI sanitized the exception diagnostics again. The prompt named both exact contract paths and permitted creating the output directory. All artifact, remote execution and local behavior checks remained required; 21 isolated generation tests passed at this checkpoint. Independent review accepted the diagnostics, and the coordinator separately accepted atomic mode-600 recording of the same redacted CLI result plus UTC timestamp in `artifacts/generation-last-result.json`.

## Historical text-generation successes

The user's terminal then completed real generation at **11:24:45.186185 UTC / 13:24 Europe/Zurich**. The locally saved result reports `generated_and_host_validated`; the downloaded source AppSpec contains **2679 bytes** with SHA-256 `71c8cab77a697797ab4f78c4fdd6433800abca447867d4bd81e86c1e0ed61e4a`. The accepted code requires paired managed code execution for the downloaded hash and independent host validation before returning this result. Its success record does not retain raw provider traces, usage or elapsed time, so these quantities are not claimed for this run.

The actual artifact was reread independently of the generation job at **11:27:03 UTC**. Its hash/size match the result record. It defines a ten-second Tap Sprint game: Start resets and starts the timer, each Tap increments score by one, expiry navigates to the final score, and Again starts a fresh round. The trusted five-check scenario passes. Additional reference-runtime checks establish 100 taps scoring 100, rejection of the exact-deadline tap, restart reset, rejection of a stale previous-round event, shell pause/resume, and zero-tap expiry without input. The original artifact remained unchanged. Detailed local evidence is in ignored `artifacts/verification/generated-app-host.json`.

This is actual model generation and downloaded-package evidence, plus host behavior verification. It does not prove Gradium speech, Android input, C-runtime parity or physical installation. The earlier three failures remain unclassified: the corrected prompt preceded success, but correlation does not establish their cause. No automatic budget escalation or fallback was needed for this successful run.

A second real text generation passed at **11:29:29.625198 UTC**, producing 2686 bytes with SHA-256 `b5900fde88b521c402acbaaf98c43654727ffd72d5f882cf43c2fee2a5becc45`. It replaced the latest generated-app file. The detailed first-artifact checks above remain evidence for the earlier hash, not this replacement.

## Android voice failures and the current authoring correction

Three actual Android audio attempts reached nonempty Gradium transcripts, then failed generation before publication. Their observer archive is `artifacts/verification/android-voice-attempts-20261010T1153Z.json`. The running service recorded generic errors; these observations do not establish the individual failure causes or transcription accuracy.

The reviewed [replay tool](../../scripts/replay_generation.py) reads the latest failed phone request without altering the deployment store, verifies frozen media hashes/sizes, and generates without publication. Three normal-terminal replays supplied actual diagnostics:

| Replay | Limit | Noncached tokens | Elapsed | Result and execution evidence |
|---|---|---|---|---|
| Original production context | 32,768 | 33,948 = 137,641 total − 103,693 cached | 86.755 s | Incomplete; seven function-call/result pairs and three code-execution pairs |
| First compact-context revision, result dated 12:14:16 UTC | 50,000 | 53,774 = 173,141 total − 119,367 cached | 154.540 s | Incomplete; eleven code-execution pairs; no generated artifact accepted |
| Readable guide and quoted JSON commands, result dated 12:23:45 UTC | 50,000 | 58,011 = 63,957 total − 5,946 cached | 136.515 s | Incomplete; two successful code-execution pairs and a trusted-check hash, but no artifact retrieved or accepted |

All three exceeded their respective noncached-token limits. This establishes budget exhaustion for these replays, not a retrospective diagnosis of the earlier generic failures. Antigravity counts input/output/thinking tokens, excludes cached tokens, and may exceed the best-effort limit between steps. [Official budget controls](https://ai.google.dev/gemini-api/docs/antigravity-agent#budget-controls)

The second replay's bounded private execution trace exposed concrete wasted work: a 9,049-byte single-line guide was truncated to 74 output bytes, a later schema dump hit 8,192 bytes, shell expansion changed `$defs` into an empty key, and a Python literal containing JSON `false` raised `NameError`. The private trace was archived before replacement; the safe result is `artifacts/verification/voice-replay-budget-20261010T1214Z.json`. Raw transcripts and commands remain private.

The latest correction replaces that bundle with the bounded readable guide described above. Its exact bash recipe uses a quoted `APP_JSON` heredoc to write JSON, then invokes `python3 /workspace/trusted_check.py` separately. It avoids the observed shell expansion and JSON/Python syntax confusion. The 50,000-token limit, 180-second deadline, two-repair maximum, canonical mounts, exact downloaded hash, paired execution evidence and trusted host behavior checks are unchanged.

Independent review accepted **25 generation tests**, including execution of the actual command templates against the relocated mounted checker: a changed 15-second/title app containing JSON `false` and literal `$defs` passes and preserves exact bytes; a wrong-score variant fails. The third live replay then confirmed complete guide output, successful JSON writing and actual trusted-check output. It still ended incomplete; no package from these voice replays has been published or installed.

The subsequent terminal-artifact recovery change passed independent review and **29 generation tests**. Only `completed`, or terminal `incomplete` with a paired successful checker hash, can enter the download path. The Files API must provide the actual app bytes; their hash, source version, schema and runtime behavior are still checked locally. Invalid incomplete artifacts fail without repair or continuation. Private traces retain the actual provider status and progress explicitly distinguishes checking a produced file from agent completion. Google documents preserved work after budget exhaustion and direct downloads from the environment; live availability still requires a real test. [Budget controls](https://ai.google.dev/gemini-api/docs/antigravity-agent#budget-controls), [Environment Files API](https://ai.google.dev/gemini-api/docs/agent-environment)

## Measured speech-profile comparison

Before the profile change, the preserved recording generated two actual downloaded apps: **12:31:36 UTC**, 1,392 bytes, SHA-256 `03f433394a2ad8967f1d8e8e82722fd4a8b8bde74ca6e0a949ce98efd9d9bfab`; and **12:33:49 UTC**, 1,627 bytes, SHA-256 `a1dc0d870e2b7acc14ce8f3ba0f5bafce792f7f4cf992d5aac074b172697eac1`. Both provider runs were completed with two execution pairs, consuming 30,101 and 33,008 effective tokens respectively. Neither exercised incomplete-artifact recovery. Exact hashes and generic host checks passed, but actual-ID scenarios showed scoring after expiry and no score reset; the second also restarted the timer on each scoring press. These apps were not published or installed. The incorrect transcripts failed to activate the stricter tap-game requirements.

At **12:35:28 UTC**, the reviewed [speech comparison probe](../../scripts/probe_speech.py) sent the same decoded recording to two fixed Gradium profiles. Baseline English transcription took 7.896 seconds and did not identify a tap game. The context profile took 6.782 seconds and recognized the tap-game phrase and requested title while preserving the 15-second duration. Some other words remain imperfect; this is one recording, not a general accuracy benchmark. Both transcripts stay private.

The selected context uses the neutral runtime words `tap`, `timer`, `countdown`, `score`, `button` and `toggle` (lowercase and initial-capital variants), boost 2 and `delay_in_frames: 16`. No requested title is injected and no transcript is silently rewritten. The production adapter selects this measured profile and the coordinated service restart has completed. Source inspection plus that restart establish the selected configuration; a per-call profile echo is not retained. Gradium supports these settings in REST `json_config`; delay accepts 0–80 frames and defaults to 10. [Transcription settings](https://docs.gradium.ai/guides/transcription-settings) Keyword matching uses individual tokens and is case-sensitive; stronger boosting can distort output. [Keyword-boosting recipe](https://docs.gradium.ai/guides/recipes/keyword-boosting)

## First generated Android installation and reboot

The observer first saw the new Android job at **12:47:16 UTC**. It reached generation at **+8.442 seconds**, validated/published readiness at **+81.118 seconds**, and exact physical active acknowledgment at **+90.598 seconds**, on **12:48:46 UTC / 14:48 Europe/Zurich**. These times start at the observer's first sight of the job, not the user's button press. The provider itself reported `completed`, attempt 1, two paired code-execution calls/results, 38,020 total tokens and 13,994 cached tokens: **24,026 effective tokens**. This successful run did not exercise incomplete-artifact recovery.

| Identity | Verified value |
|---|---|
| Generated app | `rocket_tata`, source version 1 |
| Source SHA-256 matched to paired remote checker | `0dc7e8ab9afca3e14b0aed5dc53251237375cdbe0dc93161c293b5c59734cff4` |
| Published deployment | Sequence 6, version 1, 1,307 bytes |
| Served-byte SHA-256 matched to device ACK | `8f86a3239381b9592960b8716b81e1c5835551508d4c2f236a7bb4cd843ea9dd` |

The hashes differ because publication assigns the version and serializes the final served package. The source hash comes from the trusted generation result retained by the deployment store; the actual served bytes were read through a read-only SQLite snapshot and independently validated. The archived provider trace matches the source hash. Local evidence is `artifacts/verification/phone-generated-20261010T1247Z-app.json`, the corresponding `-host.json` and `-observation.json`; the raw execution/transcription archive remains private with mode 0600.

The requested title **Rocket Tap** became **Rocket Tata**. The retained transcription contains the ordinal `15th` and `top`, so production extracted `tap_game: false` and no duration; generic runtime checks ran. Independently applying the intended 15-second tap scenario to the exact published bytes afterward passed five checkpoints. Additional checks passed for 100 scoring taps, the exact-deadline tap being ignored, score reset, stale-event rejection, shell timer suspension and zero-tap expiry. This distinguishes original production coverage from later intended-behavior verification and does not establish full transcription accuracy.

The coordinator observed all four device ACK stages ending in active. The user confirmed Start, scoring taps, a final score after 15 seconds, Play again resetting score/countdown and the phone's installation confirmation. After an ordinary reboot without flashing, the same app returned and another game started. The exact served package also passed the native C parser with address/undefined-behavior sanitizers; that native check was parsing only. [Physical evidence](hardware-probe.md)

This establishes one generated replacement after the earlier bring-up fixture, working physical game controls and ordinary reboot persistence. Title fidelity remains failed. A photo-plus-voice request for **STAR TAP**, 20 seconds, is being prepared as the next visual test; no result is claimed here. Full visual-input acceptance, three repeated successful runs and physical interruption/failure recovery remain open.
