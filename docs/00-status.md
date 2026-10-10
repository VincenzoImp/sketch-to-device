# Project status

Updated: 10 October 2026. **Current task (D32): save Penguin Tap, publish the reviewed work, fix remaining bugs, then let the user repeat the end-to-end flow.** The earlier submission deadline no longer limits this stabilization task. Gemini inside the product authors apps; the coordinator supplies its tools/runtime, without hand-written game substitutes.

## Current working state

- Runtime 0.3.0 is flashed and connected through the Android cellular hotspot. Its authenticated capability report matches the built ELF and advertises schema 1/2 and `p4-canvas-1`.
- **Penguin Tap version 3 is active**, sequence 19, with exact device acknowledgment of SHA256 `fb6d910813c529ede5c5ee478d8aa0e694e92f6823d2e5025e20f839f78c4156`. The coordinator republished the previously Gemini-authored sequence 17 source/assets unchanged under a fresh version after trusted native execution passed. Actual reset/boot restoration passed, and a failed replacement recovered this exact version. These checks are not physical gameplay or a fresh one-action generation proof.
- The exact app, original source, matching configured firmware and consistent SQLite snapshot are saved privately in `private/saved-apps/penguin-tap-v3/`. Independent review matched hashes, source provenance, active identity and database integrity. Configured firmware, database, credentials and input media are excluded from publication.
- Earlier Android voice → Gradium → Gemini → Rocket Tata passed physical play and reboot. Photo-only Star Tap and text Hello Colors passed physical interaction. Those are schema 1 results, not evidence for every programmable SDK feature or combined media.
- Latest verified public checkpoint: [99b2be5](https://github.com/VincenzoImp/sketch-to-device/commit/99b2be55c97addeb731e6f6b848b5c4df65dfb2f), 209 reviewed files, retaining the earlier history. See [the ledger](12-work-ledger.md) for subsequent publication receipts.

## Stabilization scope

The first programmable activations exposed a reproduced checkpoint-identity race during the screen switch. The minimal independently reviewed fix is now flashed and Penguin Tap reached exact active acknowledgment. The real owner regression reproduces the old failure when only that fix is removed; the corrected 36 persistence cases and 100 lifecycle cycles pass. Full target build and guarded flash passed. These checks do not replace physical gameplay.

The live service and flashed runtime now contain actionable bounded native errors, correct repeated-failure detection, prompt supersession checks, browser recovery fixes and backend-only restart without endpoint changes. The actual restart retained public HTTPS and the saved app identity; 321 host tests and the target build passed. A same-source physical replacement exposed an initialization `execution_budget` failure; the previous Penguin recovered correctly. The startup correction is independently accepted and cross-built; guarded activation and a measured replacement retry remain before the user's retry. The earlier colon cancellation route returned 404; the latest documented slash-route probe returned 400 and matching readback still reported requires_action. Remote termination remains unconfirmed.

The SDK currently exposes ordinary JavaScript with canvas, input, time and packaged image assets. There is no per-app firmware compilation. Camera, microphone and speaker APIs for generated apps are not implemented. Broad app ideas depend on the available SDK and physical resource limits; neither documentation nor an agent prompt creates a missing native API.

Flash-Lite remains the selected default. One controlled earlier task took 40.007 seconds versus Flash's 139.112 seconds, with identical correct behavior; this is not a general speed ranking. Measure fresh generation, tools and delivery separately. Inputs support text, image and audio alone or together; reviewed upload bounds are three files, 20 MiB each/32 MiB total, audio 60 seconds and video 30 seconds. Fresh Android coverage of expanded limits and combined media remains open.

The [release plan](16-final-platform-plan.md) owns acceptance gates, [readiness](11-readiness.md) owns access and missing observations, and [handoff](09-session-handoff.md) owns reading paths. Full filesystem/network access is available; do not ask the user to repeat routine Terminal work based on historical restrictions.
