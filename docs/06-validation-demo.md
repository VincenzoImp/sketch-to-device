# Acceptance checks and live demo

These checks define complete-product acceptance. The [work ledger](12-work-ledger.md) records partial evidence, including actual managed generation and the user-confirmed built-in tap app on the physical board. Neither establishes the complete Android-to-device flow. The priority is one new input producing one real interactive app, with Google DeepMind and Gradium used substantively.

## Required product evidence

| ID | Scenario | Observable pass condition |
| --- | --- | --- |
| A1 | English concept from Android, including a sketch | Upload succeeds; transcript and visual interpretation capture the requested title and behavior |
| A2 | One Generate and install action | No required clarification/confirmation blocks a supported concept; generation reaches the selected device |
| A3 | Real agent work | An actual validator/scenario command executes, with result linked to the returned artifact |
| A4 | Genuine generation | A new title or duration affects a newly generated package, rather than selecting a canned fixture |
| A5 | Physical execution | Start, timer, tap score and results work on the Waveshare touch display |
| A6 | Accurate delivery state | Companion reports active only for a matching device/job/app/version/hash ACK |
| A7 | Partner contribution | Gradium’s transcript supplies a requirement used by Gemini; trace records both real providers |
| A8 | Repeatability | Three consecutive complete runs from new input with recorded end-to-end timings |

For a text-only fallback, a tested app-specific Gradium TTS contribution can establish two-partner evidence, but A1's multimodal-input requirement remains unmet. Report partial acceptance; only the user's explicit acceptance of reduced scope changes the completion target. A file upload labeled video must actually be interpreted visually; extracting only audio does not pass the sketch requirement. See [fallback decisions](10-decisions.md).

## Runtime and transport checks

| Case | Expected behavior |
| --- | --- |
| Malformed, oversized, unknown-version or unsupported-action AppSpec | Rejected before activation; previous app remains usable |
| Duplicate IDs, missing screen/state/timer references | Rejected by trusted semantic validation |
| Two generated app variants | Distinct UI/behavior appears without reflashing the firmware |
| Timer finishes while tap events are queued | Deadline semantics prevent scoring after the game ends |
| Pause/resume/reset and navigation | Headless scenario execution and device follow the canonical contract; compare interactive preview too if that optional feature is implemented |
| Repeated install request or repeated ACK | No duplicate install or inconsistent version |
| New generation while another job is running | Explicit queue/rejection/cancellation behavior; no cross-job artifact mixing |
| Device disconnected | Job can be ready; delivery remains pending, never falsely active |
| Interrupted download | Incomplete staging package ignored; previous active package survives |
| Reboot after activation | Same package selected; transient variables reset as specified |
| Failed new UI activation | Recovery to previous package or firmware shell remains accessible |
| Wrong session/device token | Pairing, download and install request denied |

Fault injection should test the designed recovery boundary without unnecessary device wear. Document a manual power-loss procedure before running it; repeat only when a relevant change warrants it. A hardware check must include observations from the board, not just host logs.

## Provider and media checks

- Use one real file captured on the actual Android phone. Confirm the uploaded MIME/container is decodable; derive WAV bytes rather than relabeling the original file.
- Handle missing audio, silence, unsupported format, oversized file and conversion timeout with actionable errors.
- Parse Gradium NDJSON across arbitrary network chunk boundaries; reject a stream error even after HTTP 200. A partial transcript is not success.
- Confirm Gemini media processing reaches a usable state, and the managed agent returns a downloadable artifact. Test failure, cancellation and budget exhaustion without marking them complete.
- Run the trusted backend validator on every downloaded AppSpec. Agent-generated test reports are useful evidence but do not override trusted validation.
- Do not include input media, provider headers or account PDFs in public logs. Use opaque IDs and measured durations.

## Proposed demonstration

Working name: **Sketch to Device**. Explain the idea in one sentence: “Show your idea, describe it once, and turn this blank device into a working app.”

Candidate input, in English, accompanied by a simple three-screen sketch:

> Build a game called Tap Sprint. Show a start screen, then give me ten seconds to tap a big button as many times as possible. Show the countdown and score. When time runs out, show my final score and a Play again button. Use a dark background and bright green buttons.

This prompt is a demo fixture, not a hardcoded application. Ask for a different title or duration during rehearsal to prove the generator follows the input. The precise generated layout can vary within supported primitives.

1. Show the connected device and paired target in the companion.
2. Use a sketch photo and a short English voice note for the first rehearsal. A video can also be submitted, but the current implementation uses only its midpoint image and spoken audio; keep the sketch visible at that point.
3. Press Generate and install once. Explain real progress: transcription, interpretation, construction, checks, delivery.
4. When the device activates the app, play one ten-second round and show the score.
5. Explain that the firmware stays in place while a newly generated application package changes the device’s behavior.

The pitch length is not known. Prepare a 90-second explanation plus generation time, and shorten it after receiving the actual slot duration. Do not promise an instantaneous result until measured. A second conversational edit is optional and should not displace the primary one-shot demonstration.

## Evidence and fallback assets

Save one sanitized successful trace containing an input summary, provider names and measured stages, elapsed times, schema/validator versions, artifact hash and exact device ACK. Keep raw provider resource identifiers, prompts and recordings private. Record a short video of the full real path and a recovery demonstration. Keep the exact working package and configuration locally before temporary accounts expire.

Fallback order:

1. Video format failure: photo + English voice, clearly described.
2. Camera permission failure: native picker/gallery upload; keep the same processing pipeline.
3. Provider interruption: retry within the stated budget; show the failure if it persists.
4. Network/device failure: show an explicitly labeled recording of the successful physical run and/or a saved package. This is backup evidence, not a live success.
5. Simulator only: useful to demonstrate generation and behavior, but the physical-device requirement remains incomplete.

## Delivery checklist

- Competition opt-in completed by 19:00 using the actual organizer process.
- App and firmware versions frozen before the 17:00 user target, with feature freeze at 16:00.
- README contains tested setup/build/flash/run commands once implementation exists.
- Provider configuration comes from private environment settings; exported artifacts contain no credentials.
- Project code, AppSpec schema, sample artifacts, traces, demo video and pitch are exported from temporary services.
- Working and unimplemented capabilities are stated accurately. Camera/battery availability does not imply on-device capture or battery runtime has been tested.
