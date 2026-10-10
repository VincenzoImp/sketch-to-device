# Project status

Updated: 10 October 2026. **Current task (D32): save Penguin Tap, publish the reviewed work, fix remaining bugs, then let the user repeat the end-to-end flow.** The earlier submission deadline no longer limits this stabilization task. Gemini inside the product authors apps; the coordinator supplies its tools/runtime, without hand-written game substitutes.

## Current working state

- Runtime 0.3.0 is flashed and connected through the Android cellular hotspot. Its authenticated capability report matches the built ELF and advertises schema 1/2 and `p4-canvas-1`.
- **Penguin Tap version 3 is active**, sequence 19, with exact device acknowledgment of SHA256 `fb6d910813c529ede5c5ee478d8aa0e694e92f6823d2e5025e20f839f78c4156`. The coordinator republished the previously Gemini-authored sequence 17 source/assets unchanged under a fresh version after trusted native execution passed. This emergency restoration is not a fresh one-action generation proof. Physical gameplay and ordinary reboot of this JavaScript app still need user verification.
- The exact app, original source, matching configured firmware and consistent SQLite snapshot are saved privately in `private/saved-apps/penguin-tap-v3/`. Independent review matched hashes, source provenance, active identity and database integrity. Configured firmware, database, credentials and input media are excluded from publication.
- Earlier Android voice → Gradium → Gemini → Rocket Tata passed physical play and reboot. Photo-only Star Tap and text Hello Colors passed physical interaction. Those are schema 1 results, not evidence for every programmable SDK feature or combined media.
- Latest verified public checkpoint before the pending firmware checkpoint: [4c3f12e](https://github.com/VincenzoImp/sketch-to-device/commit/4c3f12e8c273e4fc2cc7f8108f55af861a4ac389), 202 reviewed files. See [the ledger](12-work-ledger.md) for subsequent publication receipts.

## Stabilization scope

The first programmable activations exposed a reproduced checkpoint-identity race during the screen switch. The minimal independently reviewed fix is now flashed and Penguin Tap reached exact active acknowledgment. The real owner regression reproduces the old failure when only that fix is removed; the corrected 36 persistence cases and 100 lifecycle cycles pass. Full target build and guarded flash passed. These checks do not replace physical gameplay.

Remaining work is to investigate slow repair loops with generic runtime errors, reconcile superseded provider work and remote termination, measure actual JavaScript replacement/resource behavior, and make the fresh user flow reliable. The current managed cancellation route returned 404 and remote termination remains unconfirmed. Preserve the running app, service, hotspot and restore images while resolving these issues.

The SDK currently exposes ordinary JavaScript with canvas, input, time and packaged image assets. There is no per-app firmware compilation. Camera, microphone and speaker APIs for generated apps are not implemented. Broad app ideas depend on the available SDK and physical resource limits; neither documentation nor an agent prompt creates a missing native API.

Flash-Lite remains the selected default. One controlled earlier task took 40.007 seconds versus Flash's 139.112 seconds, with identical correct behavior; this is not a general speed ranking. Measure fresh generation, tools and delivery separately. Inputs support text, image and audio alone or together; reviewed upload bounds are three files, 20 MiB each/32 MiB total, audio 60 seconds and video 30 seconds. Fresh Android coverage of expanded limits and combined media remains open.

The [release plan](16-final-platform-plan.md) owns acceptance gates, [readiness](11-readiness.md) owns access and missing observations, and [handoff](09-session-handoff.md) owns reading paths. Full filesystem/network access is available; do not ask the user to repeat routine Terminal work based on historical restrictions.
