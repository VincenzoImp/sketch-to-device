# Programmable platform audit and release plan

Audit date: 10 October 2026. **Implementation and physical probing are paused at the user's request while this plan is reviewed.** This document owns the next release scope and order. It supersedes the immediate next steps in the earlier [platform exploration](15-programmable-apps.md), while preserving its research and probe evidence. Planning a release is not evidence that its capabilities exist.

## Conclusion

The current limitation is architectural. The deployed AppSpec interpreter offers predefined screens, widgets and actions. More documentation, tokens or a stronger model cannot give an app drawing, calculations or timers that the firmware does not expose. That interpreter was our implementation choice for the initial demonstration; it was not the user's intended final product boundary.

Keep the working board stack, companion, provider adapters and authenticated package transport. Add a second, genuinely programmable app format: **JavaScript on QuickJS-NG, ordinary LVGL controls, a 2D drawing surface, pointer input, time services and packaged images**. One common SDK must support the requested applications; do not implement a separate template or native handler for each game. Continue loading existing AppSpec apps.

This removes the present restrictions on application logic and composition. It does not supply a browser, arbitrary npm packages, unrestricted drivers, unlimited memory or guaranteed first-attempt correctness. Hardware access becomes available through implemented and tested services. The six requested examples are feasible design targets on this architecture, not yet working programmable apps on the board.

## What the evidence establishes

- **Working production path:** Android voice and separate photo-only requests generated interactive AppSpec games, with exact device acknowledgments and user-confirmed controls. The voice-generated game survived an ordinary reboot. Voice title fidelity was imperfect; a combined photo-and-voice run remains unproved.
- **Latest successful request:** runtime 0.2 was flashed, and the fresh Hello Colors request became sequence 12. The exact 847-byte served package has SHA256 `c956a0b86a66d6d5795435ca6d71e0d6f271c3ddc99eb2409f6123c2a8693a59`. Independent host checks passed the initial color and six presses; the user confirmed the device behavior. The active ACK arrived 38.304 seconds after the observer first saw generation, not after measured phone submission.
- **Observed limitation:** the next Flappy Bird request returned `unsupported_request` for `freeform_layout`, preserving Hello Colors. Its 56.583 seconds comprised 52.837 seconds managed generation, 3.729 seconds artifact download, 13ms preparation and 4ms checks. There was no app firmware compilation. Calling an earlier package “Flappy Bird” would not establish its mechanics.
- **Language feasibility:** the [engine proof](../firmware/probes/quickjs/README.md), [host UI proof](../firmware/probes/programmable-ui/README.md) and [P4 target build](../firmware/probes/programmable-target-ui/README.md) establish real JavaScript execution, bounded engine resources, labels/buttons, computed callbacks and host recovery. The target adapter cross-compiles; it has not run on the physical board or delivered a generated script through the product.
- **Speed evidence:** the same Hello Colors task passed with identical bytes in 40.007 seconds using Flash-Lite and 139.112 seconds using Flash. This single comparison supports the selected default, not a general model ranking. [Recorded comparison](15-programmable-apps.md#generation-latency-and-model-choice).

The source-level audit inspected the actual renderer, runtime, delivery state machine, generator, media handling, companion and accepted interpreter bindings. Hardware, agent/media and system-delivery lanes examined different seams; the coordinator reconciles their findings. No new flash, provider generation or service restart is part of this audit.

## Material gaps and decisions

| Area | Actual limitation and consequence | Release decision |
| --- | --- | --- |
| Application language | [AppSpec](../firmware/main/app_spec.h) has scalar state and fixed actions, without general expressions or callbacks | Replace it as the default authoring target for capable devices; retain its loader for compatibility |
| Graphics | [Renderer](../firmware/main/app_ui.c) stacks fixed widgets; it has no moving scene, image assets or arbitrary drawing | Add one bounded canvas API plus dynamic controls, rather than more game-specific actions |
| Events and time | The JS proof exposes button clicks, but no scheduler, pointer coordinates or explicit clock-quality API | Add shared monotonic timing, frame callbacks, pointer events and a separate wall clock |
| Production JS integration | The proof contains trusted programs, with no production package, durable activation or generated-script delivery | Integrate one versioned package/lifecycle contract before advertising programmable support |
| Native execution | Interpreter limits do not bound all native drawing or LVGL allocations; the proof drains callbacks while holding the display lock | Bound dispatch and native work, reserve system responsiveness and measure actual memory headroom |
| Agent knowledge | Mounted SDK is selected from backend source, not fresh installed-device capabilities | Select an exact SDK from an authenticated, fresh device report; never silently generate for an unavailable API |
| Intent fidelity | [Generation checks](../backend/generator.py) cover structure and narrow tap/duration/name heuristics, not general user intent | Replace category-specific inference in the new path with request-derived scenarios and practical execution; retain trusted safety checks |
| Execution evidence | The paired remote marker can be printed without actually invoking the mounted checker; independent local checks remain authoritative | Treat it as correlated tool output, not attestation; bind real trusted-runner receipts to package hash, SDK and scenario |
| Media and assets | Images are perception inputs; normalized JPEG loses alpha. There is no source-image-to-device-asset path | Preserve frozen originals privately; create verified resized/cropped assets separately from perception images |
| Delivery health | [ACK store](../backend/deployments.py) treats active as terminal; later callback failure cannot update current health/rollback truth | Add a separate durable health/recovery report with exact restored identity and idempotent handling |
| Diagnostics | Normal service does not retain the generator's optional per-call timing report; last-trace files are overwritten | Persist safe per-job phase timings and correlate provider run, package, device activation and failure |
| Service recovery | A restart fails active local jobs without durable provider-handle reconciliation; phone progress omits intermediate device ACKs | Persist/resume or explicitly cancel the same remote job; distinguish generation, delivery, last installation and current health |
| Browser recovery | Fetch has no per-request deadline; an unknown saved job can keep offering Resume; partial uploads are not resumed | Bound each request, clear terminal unknown-job state safely and retain accepted-job idempotency; disclose interrupted upload rather than duplicate generation |
| Operational setup | A new temporary tunnel URL requires private configuration update and firmware rebuild | Keep the live endpoint now; provide a stable service address for repeatable release setup, and test restart/reconnection without reflashing |

Do not discard the already useful parts: separate session/device authentication, frozen request inputs, provider keys on the backend, hosted speech, managed tool execution, exact served-byte hashes, stale-intent checks, two-slot package persistence and the one-action phone experience.

## Shared capability contract

The names below describe the proposed API surface, not callable production APIs. Freeze signatures, error behavior and resource units in one versioned manifest during milestone 1; derive the mounted SDK and tests from that contract.

| Surface | Required behavior | Boundary |
| --- | --- | --- |
| Language | Variables, arrays, functions, conditions, arithmetic and bounded asynchronous callbacks | Pinned QuickJS engine; no host OS modules, credentials or raw native pointers |
| Controls | Positioned labels/buttons, mutable text/colors/geometry, visibility and enabled state | Owned handles, clipping, finite values and measured object/text quotas |
| 2D graphics | Clear, rectangles, lines, text and immutable images; frame commands submitted in a batch | One native canvas per app scene; command/pixel/text budgets; no per-pixel JS/native call loop |
| Input | Single pointer down/move/up/cancel in app-local coordinates, plus control events | Activation-tagged copied values; coalesced moves; release/cancel and system Home remain serviceable |
| Scheduling | Monotonic milliseconds, periodic/frame callbacks, cancellation, pause/resume/dispose | Coalesce late ticks, bounded catch-up, no callback backlog; separate game time from elapsed time |
| Wall clock | Epoch time with validity/source and explicit timezone/offset configuration | Build-time TLS bootstrap is not accurate time; offline/reboot uncertainty is visible |
| Assets | Manifest-bound image handles with source provenance, dimensions, format and content hash | Backend conversion, bounded decoded size, no app-provided filesystem paths or remote URLs |
| Lifecycle | Hidden candidate preparation, activation, Home, cleanup, previous-app recovery and boot quarantine | One interpreter owner task; stale callbacks and handles cannot cross activations |

LVGL 9.4 already supports canvas drawing into caller-supplied buffers, including shapes, text and images. It is not thread-safe; access must obey the BSP locking/ownership model. Reuse those implementations rather than building a rasterizer. [Official canvas documentation](https://docs.lvgl.io/9.4/details/widgets/canvas.html), [threading documentation](https://docs.lvgl.io/9.4/details/integration/overview/threading.html). QuickJS provides embedding/resource hooks, not a device UI or process-level security boundary. [Official C API](https://quickjs-ng.github.io/quickjs/developer-guide/intro/).

Keep the current 320×432 app viewport and system-owned 48px header until a smaller persistent Home affordance is physically qualified. A gesture alone is insufficient recovery. Put connection details in system status, show useful installation/error progress, and let each app own its visual design inside the safe area. A richer launcher/library can follow; the current two slots are not a general installed-app library.

### Memory, rendering and resource limits

The installed BSP drives this panel over 80MHz single-line SPI. One 320×432 RGB565 canvas occupies 276,480 bytes; sending all of it has a 27.648ms arithmetic lower bound before rendering/protocol costs. Do not promise 60fps. Measure representative 20fps and 30fps scenes; choose and report the supported performance envelope from the physical result.

The accepted staging proof can retain **previous, live and candidate** runtimes at once. Budget all three engines, native objects, framebuffers, assets, renderer scratch and network/display reserves; do not treat the JavaScript heap ceiling as total app memory. Inspect internal RAM and PSRAM free bytes and largest blocks separately. Native LVGL failure paths remain outside full graceful-OOM containment. Conservative admission, bounded APIs and measured headroom are necessary; full widget preallocation is not yet shown to be the smallest required solution.

Run JS computation outside the display lock where possible; acquire it for bounded native updates/scene swaps. Preserve callback ownership and object lifetime while doing so. Reserve a system-control path and dispatch budget so an app event flood cannot indefinitely delay Home. An interrupt hook cannot stop a long native drawing call: validate and bound that work too.

### Packages, storage and rollback

Introduce a distinct script envelope with source text, engine/SDK identity, required capabilities and hashed asset entries. Preserve schema 1 compatibility and the existing publication/device identity checks. Never accept agent-supplied bytecode, firmware, native modules or validation claims as trusted artifacts.

For the first image proof, stay within the existing 64KiB package envelope and 512KiB dedicated storage region if two complete packages plus metadata/compaction demonstrably fit. A 64×64 RGB565A8 image is 12,288 decoded bytes and can serve many on-screen positions. A 128×128 version is 49,152 bytes; base64 alone reaches 65,536 characters before source/metadata, so simply raising the photo upload limit cannot solve package storage. Keep source upload limits, agent input limits, package size and decoded memory as separate budgets. RGB565A8 has separate color/alpha planes; conversion must match LVGL stride/color order.

Before broadening asset capacity, benchmark the actual package distribution and make an explicit storage choice with backup/migration and two recoverable packages. Do not silently erase NVS, repartition the running board or claim an arbitrary asset library. All six reference apps can initially exercise the common API with small assets; that is a first resource envelope, not a whitelist of permitted apps.

The production lifecycle must reconcile durable package commit with owner-task preparation/activation. Test power interruption around every commit boundary. A callback exception after `active` needs a health event reporting the failed activation and the exact recovered package, including across reconnect/reboot. An in-memory previous root is not durable recovery. Add a boot-failure marker/quarantine to avoid reopening the same crashing app forever. App package persistence is separate from persistent user data such as high scores.

## Agent workflow and useful context

1. Freeze the request and attachments; transcribe speech with Gradium and preserve explicit text/labels. Resolve the target's fresh runtime/SDK/capabilities. If offline, wait or fail clearly; do not silently use the newest backend SDK.
2. Start Gemini with a short task, exact available API manifest, a minimal runnable skeleton and links to relevant local references. Include all consulted documentation in a searchable SDK, not a compulsory reading checklist. Keep Flash-Lite as the measured default with the generous 200k-token/600-second profile; budgets are ceilings, not targets to consume.
3. Let the agent write ordinary code, run it early, inspect diagnostics/screenshots, test requested behaviors and repair concrete failures. Provide separate concise guides for UI, game loops/input, timing, images and lifecycle. Examples teach APIs; they must not select canned app behavior in place of the request.
4. Use Google Search/URL context for specific unknowns, with the pinned SDK authoritative for callable device APIs. These tools are declared locally but their successful use with the live account still needs observation. External content is data and cannot alter tool permissions or expose secrets.
5. Run the same pinned engine/native bindings on a host with injected clock, pointer and RNG seed. Resolve the checker route in the prerequisite gate below. Backend execution and repair feedback remain necessary even when the agent can also run its own checks.
6. After generation, the backend independently checks actual bytes, compatibility/resources and meaningful scenarios, then publishes once. Agent self-review helps; it is neither a formal proof nor a substitute for testing the installed result. General semantic correctness cannot be guaranteed by a few regexes or by a second model's approval.

Make the agent's supplied scenarios explicit and untrusted. Use independent expected outcomes for the acceptance suite, exact user-specified constants where unambiguous, and rendered/reference review where relevant. Remove the assumption that every stated number of seconds describes a countdown; a stopwatch display interval and a clock setting have different meanings. Preserve the single Generate and install action—no mandatory transcript or preview approval is added.

### Prerequisite: prove the real checker route

The current managed checker is Python/AppSpec. A macOS host executable or P4 cross-build does not establish a Linux runner inside the managed environment. Google's documented inline limits are 1MB per file/2MB total; the local QuickJS core sources already exceed that total and LVGL adds substantially more. Archive/file transfer documentation does not establish executable-binary support or compiler availability. [Official environment limits](https://ai.google.dev/gemini-api/docs/agent-environment#limitations).

Before bulk integration, run one minimal live experiment to establish either the actual same-engine remote runner or a registered backend `test_app_package` function and correlated continuation. Prefer the latter if it avoids an unproved remote toolchain: execute only JS/assets in the backend's fixed trusted runner, in a bounded child process without provider secrets or host/network APIs. Never accept model-supplied C, shell commands, native executables or a mutable verifier. Return a service-recorded package/SDK/scenario receipt and safe results; independently verify the image-result channel before claiming the agent inspected a rendered preview. The current provider adapter treats unresolved custom calls as failure, so resume handling is real implementation work.

This is actual execution through an agent tool, even if the runner lives on the backend. State its location honestly. The remote `VALIDATED_APP` text is not proof of an unmodified checker invocation: the audit reproduced an accepted matching marker from code that merely mentioned the checker path in a comment. Independent backend validation still protects existing AppSpec acceptance; the finding does not establish that an invalid app was installed. The new path must rely on attributable runner execution, not a model-printed success claim.

### Reference images and generated sprites

For “use this photo as the mole,” the first path is deterministic reuse: frozen uploaded image → oriented crop/resize → verified bitmap → package asset → display/hit test. Preserve the selected subject, alpha where present and source-to-asset identity. Keep the white-composited perception JPEG separate from the original used for asset conversion. A screenshot/reference reconstruction is a different task from directly reusing an image; the SDK must explain both.

A Google image-generation broker can later produce new sprites from selected references. It needs an actual API call, function-call/resume integration, conversion and the same asset checks. It is not a built-in capability gained by listing a tool name, and it is not required for the uploaded-image mole. Do not block the six-app release on image-model latency, transparency quality or camera support. [Official managed-agent tools](https://ai.google.dev/gemini-api/docs/antigravity-agent), [image generation](https://ai.google.dev/gemini-api/docs/image-generation).

The current source accepts up to 3 files, 20MiB each/32MiB total, 60 seconds audio and 30 seconds video, with bounded photo normalization. Larger uploads mainly affect phone transfer, decode/transcription latency, backend memory/storage and provider payloads; they do not expand device capabilities. Keep these reviewed limits until fresh Android tests reveal a concrete need. Add per-job timings for upload/preparation, speech, managed execution, download/checks, publication and device activation. Do not present managed wall time as pure model compute or overwrite the only trace of the preceding job.

## One release, implemented in gated slices

These slices build the same product and SDK. They are not separate app-specific workarounds. Preserve the working 0.2 binary, app storage, endpoint and service throughout. Every slice gets a reviewed public commit; deployment occurs only after its dependencies pass.

| Milestone | Concrete output | Gate before advancing |
| --- | --- | --- |
| 0. Freeze seams and prove tool execution | Shared SDK/package/health contract and one real remote-runner or backend-test-function experiment | Exact source hash and actual frame/event result return through the chosen tool route; if neither route works, resolve that blocker before building around it |
| 1. Contract and production language path | Versioned script envelope/SDK with working JS authoring/test instructions, capability report, reusable interpreter component, owner-task lifecycle, backend checker route and durable activation/health protocol | A newly generated schema 2 JavaScript calculator/color app travels from Android through real tools to the board; a bad candidate and post-activation failure preserve/recover the correct app and report it honestly. Existing AppSpec Hello Colors and the trusted probe programs do not pass this gate |
| 2. Time, input and rendering | Monotonic/frame scheduler, pointer events, dynamic controls, canvas with bounded batched drawing and honest wall time | Clock/stopwatch semantics pass; moving shapes respond on the board; Home remains usable under load; actual frame time and internal/PSRAM peaks establish budgets |
| 3. Image path and agent authoring | Frozen-reference conversion, hashed bitmap assets, matching SDK skills, executable examples/scenarios and correlated diagnostics | A fresh uploaded photo appears as the actual tappable mole with changing positions and correct hit/miss scoring; reference transformation and exact installed bytes are traceable |
| 4. Unified qualification and handoff | Six fresh generated apps, unseen variations, recovery/compatibility tests, stable service address, coherent shell and English demo/setup documentation | The matrix below passes physically; service restart/reconnect needs no firmware rebuild; negative tests and repeated installs pass; claims, source, firmware and public history agree |

Some backend/SDK work can proceed alongside firmware after milestone 0 contracts are frozen. The initial hardware-lane estimate for lifecycle, scheduling, canvas/assets and physical qualification is **roughly 11–22 focused engineer-hours**, excluding the not-yet-sized managed-tool broker, stable hosting and additional integration failures or peripherals. This is not a complete project estimate or an elapsed-time promise. Parallel AI work does not eliminate serial hardware qualification; size the remaining backend work after milestone 0 and re-estimate after the first production script and frame-rate measurements. It cannot honestly be guaranteed by the old 17:00 target. Keep the existing demonstrated flow usable for the event.

### Release acceptance matrix

| Fresh request | Required visible result and independent checks |
| --- | --- |
| Snake | Moving body, direction input, food/growth, wall/self collision and restart; deterministic host scenario plus physical sustained play |
| Flappy Bird | Gravity/jump, moving pipes, collision, pass scoring and restart at the measured device frame rate; no renamed tap-counter substitute |
| Calculator | Enter multiple values/operations, correct results, clear/backspace and division-by-zero behavior; decimals/negative values when requested |
| Clock | Correct configured local time with source/validity, periodic updates and honest offline/reboot behavior; controlled wall-clock changes in host tests |
| Stopwatch | Monotonic elapsed time, start/pause/resume/reset and laps if requested; no drift from missed frame callbacks or wall-clock changes |
| Image whack-a-mole | The selected uploaded image appears at changing positions; only valid hits count; round completion and restart work |

Also generate an unseen combination using the same primitives, such as a reaction game with the supplied image and configurable scoring. This checks that the SDK enables composition rather than six hidden templates. Cover text-only, image-only and fresh combined photo+voice requests, including explicit labels/colors/durations. Record failures rather than silently substituting a simpler app.

Common release gates: same-engine host tests and rendered frames; legacy-app compatibility; malformed/tampered assets; timeout and Promise rejection; queue overflow/stale events; repeated switching and memory trends; candidate admission failure; download/activation interruption; exact restored identity after reconnect; reboot without a crash loop; offline app use; current-source clean build/setup instructions; three complete measured phone-to-device runs. Require physical touch/render/recovery evidence for the hardware claims. Record measured frame and Home-response times; choose acceptable thresholds from the representative workload before accepting the release, not after seeing a failure.

## Explicitly separate follow-on work

Camera, microphone and speaker have BSP/driver foundations but no generated-app API or physical proof in this project. Add each as an asynchronous service with its own small hardware test, resource budget, cancellation and system indicator before declaring it in capabilities. They are not prerequisites for the six requested applications. The same applies to arbitrary network/AI calls during app use, persistent app data, a larger app library, richer generated assets and a full-screen shell. A stable service address is included in operational release qualification; broad multi-user public hosting is separate.

Do not migrate to a new IDF/LVGL framework, implement a browser, permit raw generated firmware, or remove verification merely to make the format appear unrestricted. Those choices add separate engineering and recovery requirements. The release is complete when its general primitives and acceptance evidence pass—not when every conceivable device feature has been promised.

## Immediate handoff

Hardware, agent/media and final system/cold-start reviews accepted this audit and plan with no remaining material finding. [Status](00-status.md), [readiness](11-readiness.md), [decisions](10-decisions.md) and [ownership](12-work-ledger.md) are reconciled; the public context audit passed158 files. Publish the reviewed checkpoint using the already authorized workflow; publication is not yet established. The partial ignored physical-probe helper is parked and unreviewed; do not execute it. No new user setup, provider retry, service restart or flash is needed to complete the audit. Completing document review/publication does not itself lift the user's implementation pause. Once resumed, work starts at milestone 0, not at another AppSpec extension or an isolated flash that cannot establish the release path.
