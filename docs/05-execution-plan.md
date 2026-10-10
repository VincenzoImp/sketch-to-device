# Controlled implementation pipeline

This is the implementation runbook for the one-shot creation demo. It does not record completed implementation. Implementation is now authorized; read current gate evidence and user steering before selecting the next task. All project artifacts, interfaces, prompts, identifiers, comments and demo material are in English.

Read [session handoff](09-session-handoff.md) before resuming. Actual task/gate status and exclusive ownership are maintained in [the work ledger](12-work-ledger.md), not inferred from this schedule. [Readiness](11-readiness.md) identifies which prerequisites are resolved, tool-owned or externally blocked.

## Outcome

On an Android phone, submit one new concept through the companion and press **Generate and install** for the paired Waveshare. Google DeepMind and Gradium perform real work. The system generates and checks an interactive app, installs it on the physical display, and reports success only after the device acknowledges the exact package. No mandatory conversation, transcript confirmation or preview approval interrupts this happy path.

The first candidate is a ten-second tap game with start, countdown, score and results. This is an acceptance scenario, not a hardcoded answer that substitutes for generation. A different title, duration and layout request must affect the generated package. The runtime’s supported primitives bound what can be generated.

## Work allocation

| Owner | Responsibility | Initial file ownership |
| --- | --- | --- |
| Coordinator | Contracts, integration, decisions, acceptance and deadline | `contracts/`, root config, status, end-to-end fixtures |
| Hardware worker | BSP, runtime, transport, package recovery | `firmware/` |
| Backend worker | Provider adapters, jobs, media, validation integration, device API | `backend/` |
| Companion worker | Android UI, capture/upload, preview, job and device states | `companion/` |

The user is the sole human participant; the lanes above are AI workers, not additional teammates. Maximum concurrency: coordinator plus three workers. Review work is assigned to a worker after its implementation task finishes or pauses; do not create imaginary additional capacity. Workers may suggest contract changes, but the coordinator integrates them once and informs all consumers. No two workers own the same file at the same time.

Every task handoff states input documents, owned files, required output, acceptance checks and unresolved dependencies. Workers report evidence, not only completion claims. The coordinator keeps the shared state current and does not count an agent review as a hardware test.

## Schedule and cutoffs

Latest user target: **ready by 17:00 Europe/Zurich, 10 October 2026**, superseding the earlier 19:30 target. Feature freeze at **16:00**, with the last hour reserved for full-path verification, recovery, rehearsal and export. Official opt-in remains 19:00 and demos 20:00.

The Mac clock showed **12:41:17 +02:00** when this target was received: approximately 258 minutes remained. Recalculate from the Mac at each major gate; this timestamp is historical. Code/test evidence in [the ledger](12-work-ledger.md) determines progress, not these estimates. The user gives design latitude: choose the simplest evidence-supported route preserving the core physical one-shot experience.

| Gate | Target by local time | Exit evidence | If blocked |
| --- | --- | --- | --- |
| G0 prerequisites / G1 probes | 13:15 | Chip/revision, build route, minimal provider calls and managed artifact, frozen host contracts | Prioritize the exact failed dependency and supported alternative; keep independent integration code moving |
| G2 physical runtime | 14:00 | Two data packages run, touch/timer behavior correct, invalid package rejected | Cut optional presentation/peripherals; retain required interaction and recovery |
| G3 delivery slice | 14:30 | One phone action installs a known package, exact device ACK | Diagnose transport before adding AI; USB alone cannot pass wireless acceptance |
| G4 generated text app | 15:00 | Fresh request, real agent command, trusted checks and physical activation | Fix provider/contract failures; no cached app substituted for generation |
| G5 multimodal and partners | 15:45 | Real phone visual/spoken input affects generated app; both partners used | Photo plus speech is the declared video fallback |
| G6 feature freeze | 16:00 | Complete path works; only defects and required reliability work remain | Freeze scope and fix critical failures |
| G6/G7 verification and delivery readiness | 17:00 | Three full runs, failure/recovery checks, working configuration/export, English rehearsal | Report any unmet gate explicitly; do not relabel a simulator or fixture as completion |

These targets are checkpoints, not promises. At a missed checkpoint, recompute the critical path and make one concrete adjustment. Avoid spending the remaining budget polishing support scripts or adding optional features. Registration/submission follows the actual organizer mechanism; preparing the assets early does not prove submission.

**14:00 adjustment:** built-in touch/timer behavior works, but G2's downloaded-package requirement is not met. Actual Android audio now reaches a nonempty Gradium transcript; the two voice jobs then fail at Gemini with a generic provider response. Work in two independent diagnostic lanes: official serial monitor for the physical HTTPS failure, and one replay of the exact frozen voice request with safe provider diagnostics. A known Focus Timer package is queued to make the first successful download visibly distinguishable from the built-in game. Aim to close transport and package replacement by 14:30, generated speech-driven behavior by 15:15, and visual input plus rehearsal by 15:45. Keep the 16:00 freeze and 17:00 target. These are revised targets, not claims or permission to omit recovery checks. Do not add optional features or repeat unchanged failed attempts while either diagnosis is unresolved.

## G0 prerequisites

1. Confirm the physical board is connected through the intended USB port. Read boot/probe information and silicon revision without guessing. Establish how to restore a known baseline before overwriting firmware. Camera and battery are confirmed by the user; their operation is untested.
2. Locate or install an isolated toolchain compatible with the chosen Waveshare example. Record exact ESP-IDF tag, board repository commit, component locks and C6 compatibility. Do not change the C6 firmware just because a newer version exists.
3. Resolve a supported backend Python version. The observed system Python is 3.9.6; SDK requirements may require a separate environment. Install only the packages actually selected for the project and lock versions after successful probes.
4. Configure Gemini and Gradium secrets privately. Test access without printing credentials or copying account PDFs into any remote context.
5. Establish the phone/backend/device network route. Test HTTPS on Android and the actual device; record a recoverable network configuration. Verify FFmpeg or another real media conversion path.
6. Confirm competition opt-in procedure, pitch duration and team responsibilities. Use the requested Google DeepMind + Gradium combination; Entire remains parked unless a concrete need emerges.

## G1 contracts and independent smoke tests

The coordinator turns [contracts](04-contracts.md) into `contracts/app.schema.json`, a runtime capability document and positive/negative fixtures. Freeze field names, timer semantics, numeric limits, event ordering, versioning and ACK rules. Agree a minimum API shape before workers implement their sides.

The hardware worker runs display/touch and network checks on the real board. The backend worker verifies minimal model access, managed code execution and artifact download, trusted AppSpec generation, actual Android media conversion and an English Gradium transcription. The earlier [Gemini research](research/gemini.md) provides sources; its proposed SDK/ConceptBrief smoke-test sequence is superseded by the implemented REST and direct-image path. The companion worker verifies recording or native picker upload on that Android phone and displays truthful fixture job/device states. An interactive fixture preview is optional P1; headless behavior checks and physical interaction are required.

The managed agent must receive the actual trusted schema/validator files and return a downloaded artifact. A model reply that says it ran tests does not pass this gate. If the account cannot run the advertised managed agent, document the failure and choose the explicit alternative from the research notes; preserve the event requirement as unresolved if necessary.

## G2 and G3 runtime before generation

Build the minimum firmware shell and app interpreter. Prove that two different hand-authored packages run and can replace each other without a firmware rebuild. Include a working timer, score changes and navigation. Keep the previous package and a firmware-owned recovery screen.

Next prove phone → backend → device delivery with one known valid package. The generated-model lane is not involved yet. Check authentication, target selection, download bounds, hash, duplicate requests, activation and ACK. Show delayed/offline states accurately. After a restart the active package is still selected; transient game state may reset according to the contract.

This slice establishes whether the eventual AI output has somewhere reliable to go. Do not wait until late afternoon to attempt the first physical installation.

## G4 and G5 generation and media

Build the pipeline in small demonstrable steps:

1. Frozen text request and supported media → managed agent with the trusted runtime context → downloaded `app.json` and execution evidence. A separate structured-brief stage is deferred.
2. Trusted backend validation and scenario execution on the downloaded bytes.
3. Bind one job to one selected device and the exact frozen input. Publish only the checked package under the user’s initial Generate and install action.
4. Integrate real progress events and device ACK into the companion. Include an optional preview without making it a compulsory approval step.
5. Add English voice through Gradium. Pass the transcript into the agent's concept input without requiring confirmation. The current UI shows transcription progress; transcript display and editing are deferred.
6. Add sketch photo and then short video. Send supported photos inline to Gemini; the current video path extracts one midpoint frame plus audio for Gradium. Do not claim interpretation of a complete video sequence.
7. Confirm the complete path with a fresh spoken instruction whose effect appears on the device.

For a text-only demonstration, a tested Gradium TTS explanation of the newly generated app can provide the second partner contribution. If TTS is not implemented and tested, use spoken input for the main demo. A pure text → Gemini run must not be presented as demonstrating Gradium.

## Review and repair loops

The [active research workflow](14-autonomy-and-research.md) governs diagnosis and source gathering. The user's [quality policy](13-quality-gates.md) applies to every coherent deliverable, including docs and supporting tools. Require an independent reviewer and practical acceptance evidence; passing a mocked integration test cannot close a real provider/hardware gate.

Two different loops are involved:

- **Development loop:** implement one gate → run its acceptance checks → obtain an independent review → correct material failures → rerun the affected checks. Continue toward completion while time and dependencies allow. After two unsuccessful attempts with the same failure signature, change the diagnosis or use the documented fallback instead of repeating unchanged commands. Keep independent lanes progressing.
- **Product generation loop:** proposed cap of an initial attempt plus two AppSpec repair attempts, inside one job deadline and token allowance. Report validator errors precisely. If still invalid, preserve the previous device app and return a clear failure. Do not silently install an unvalidated result.

Current generation limits are a 60-second provider-request bound, 180-second total deadline, an initial attempt plus at most two validation repair attempts, and one active generation worker. A concurrent request receives `409 generation_busy`; queueing and cancellation are not implemented. Provider transport failures currently fail the attempt; automatic transport retries remain a possible improvement requiring evidence. The companion watches delivery for up to six minutes and allows resuming the same request. Measure physical delivery latency before setting a shorter acceptance target. Authentication errors and invalid inputs require correction, not blind retries.

The public demo target is a result within roughly 60–90 seconds, **not a measured promise**. If real generation is slower, reduce context/schema/sandbox setup and choose a truthful presentation with visible progress. A cached package is a backup, not live generation.

## Change control

A proposed new feature states user value, dependencies, time cost and acceptance check. After G3, it must improve the one-shot journey or remove a blocker. Defer onboarding polish, app libraries, arbitrary code, BLE, on-device capture, voice cloning and general games engines until the core is complete.

Record each gate as `not_started`, `in_progress`, `passed` or `blocked`, with timestamp, evidence path and next action. “Blocked” here is a project status entry, not an instruction to stop all other work. Do not mark a gate passed from documentation alone.

Use [the work ledger](12-work-ledger.md) for those records and [the decision register](10-decisions.md) for scope changes. Keep the current owner and evidence location explicit so an interrupted session can resume without repeating work.

## Completion and handoff

Complete [validation and demo](06-validation-demo.md), preserve the working configuration and export all source and artifacts outside temporary cloud accounts. Deliver exact run/build/flash instructions with observed versions, a short demo video, the accepted package and its trace, remaining limitations and the submission link if provided. Do not publish files or transcripts containing credentials.

Implementation is complete only when the agreed physical happy path works and required checks pass, or the user explicitly accepts a reduced outcome. A finished context pack or a successful compilation is not completion of the product.
