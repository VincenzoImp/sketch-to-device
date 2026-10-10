# Project status

Updated: 10 October 2026, 18:34 Europe/Zurich. **Current task: implement the reviewed programmable generation platform (D30).** The user made the published plan summary an active goal. Gemini authors apps; the coordinator builds its SDK/tools/runtime. Planning was published at`5a183fd1ca8e40012e17f61d1408b595fba27c5f`, with all158 blobs and remote main verified. The device remains AppSpec0.2. The reviewed programmable backend is now served over HTTPS and requires a fresh compatible device report before generation. Read [the plan](16-final-platform-plan.md), [handoff](09-session-handoff.md), [readiness](11-readiness.md) and [ledger](12-work-ledger.md).

## What works

- Android voice → Gradium → managed Gemini tools → exact package activation → user-confirmed 15-second game. Sequence6 Rocket Tata also restored after an ordinary reboot. The requested title Rocket Tap was mistranscribed.
- A separate photo-only request generated sequence7 Star Tap and worked physically. Its 10-second duration was a default; there was no accompanying audio. This is not combined photo/voice evidence.
- After the service restart and runtime0.2 flash, fresh Hello Colors sequence12 passed exact activation, independent initial-state/six-press checks and user-confirmed physical color cycling. The next Flappy Bird request returned `unsupported_request` and preserved Hello Colors.
- Display/touch, downloaded apps and authenticated HTTPS through the Android cellular hotspot work. Certificate verification stays enabled. The event Wi-Fi had a captive portal.
- Verified latest public checkpoint: [d11b72b](https://github.com/VincenzoImp/sketch-to-device/commit/d11b72be89a806958c8d01312d91ed4c66f8001e),190 reviewed files, matched to every committed blob and remote main. D30 implementation changes need their own reviewed checkpoints.

## Audit conclusion

The device still runs AppSpec0.2; the restarted backend targets schema2 and waits for a compatible runtime report. The replacement now has a shared QuickJS/LVGL engine, ordinary JavaScript source, canvas/input/time APIs, original-image assets and trusted execution feedback. A real managed Gemini run authored and tested a program using these services. Firmware owner integration cross-builds, but schema2 delivery/recovery integration and physical execution remain open. Context cannot expose a firmware API that has not been implemented.

The [release plan](16-final-platform-plan.md) selects one JavaScript SDK with existing LVGL controls, a bounded canvas, pointer input, time and packaged images. Snake, Flappy Bird, calculator, clock, stopwatch and uploaded-image whack-a-mole are independent acceptance cases, not six templates. Actual device capability selection, trusted execution feedback, durable runtime-failure recovery and stable service setup belong in the same release. Camera/microphone/speaker remain separate physically unproved extensions.

## Verified improvements and remaining limits

- Flash-Lite is selected and the service has restarted from reviewed source. One controlled task took 40.007 seconds versus Flash's 139.112 seconds with identical correct output; this is not a general speed ranking. Both had 200,000 tokens and 600 seconds. Current per-app firmware compilation time is zero.
- Reviewed media bounds are three files, 20MiB each/32MiB total; audio 60 seconds, video 30 seconds, bounded photo normalization. Fresh Android coverage of the larger limits remains open. Normalized visual input is not an embedded device asset.
- Host/native checks, the 176-test integration suite and isolated UI proofs passed within their documented scopes. The new public target build reproduction is independently accepted. Physical JS execution, native resource headroom and complete recovery still need evidence.
- The audit found that normal jobs overwrite the latest provider trace/timing, remote printed checker markers are not execution attestation, and post-active runtime failure needs a new recovery report. Existing independent backend AppSpec checks remain in place; no invalid installation is established by those findings.

## Next action

The real authored-code/image probe passed in155.090seconds: seven independently reproduced frames, six pointer interactions and a separate asset-mutation check. It installed nothing. Complete the capability-aware HTTP path and durable device recovery, then run the exact generated package physically. Cancellation callers match the Antigravity guide, but the official REST reference documents a different route. Actual colon-route POST requests returned404 while GET still reports requires_action. Remote termination remains unconfirmed. No new generation is needed to test the retained package physically. D31 prioritizes reviewed physical integration within the remaining thirty minutes; no peripheral expansion or input-mode narrowing is selected. Its first product proof uses a newly generated app from prompt/image, not a coordinator-written game. Wider requests and peripheral services have separate acceptance gates. Camera, microphone and speaker remain unavailable to generated apps until implemented/tested.

The user authorizes autonomous work and periodic public commits. Full filesystem/network permission is now enabled; direct Git/GitHub operations passed. Verify serial/provider operations when needed instead of repeating old restriction claims. Preserve the live demo during development; no new key or hotspot credential is needed.
