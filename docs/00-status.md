# Project status

Updated: 10 October 2026. **Current task: plan the complete generation-pipeline redesign; Gemini must author apps from the user's prompt/image. No hand-built game substitutes.** The working demo remains intact. Read [the new plan](16-final-platform-plan.md), [handoff](09-session-handoff.md), [readiness](11-readiness.md) and [work ledger](12-work-ledger.md) before resuming.

## What works

- Android voice → Gradium → managed Gemini tools → exact package activation → user-confirmed 15-second game. Sequence6 Rocket Tata also restored after an ordinary reboot. The requested title Rocket Tap was mistranscribed.
- A separate photo-only request generated sequence7 Star Tap and worked physically. Its 10-second duration was a default; there was no accompanying audio. This is not combined photo/voice evidence.
- After the service restart and runtime0.2 flash, fresh Hello Colors sequence12 passed exact activation, independent initial-state/six-press checks and user-confirmed physical color cycling. The next Flappy Bird request returned `unsupported_request` and preserved Hello Colors.
- Display/touch, downloaded apps and authenticated HTTPS through the Android cellular hotspot work. Certificate verification stays enabled. The event Wi-Fi had a captive portal.
- Verified public checkpoint before this redesign revision: [d223469](https://github.com/VincenzoImp/sketch-to-device/commit/d223469e89f2fca6057ff97c01598fa02ede3c53),158 reviewed files, directly published and matched to snapshot/remote main. Current planning changes need their own reviewed checkpoint.

## Audit conclusion

The product currently generates a fixed JSON AppSpec, not general programs. The isolated QuickJS host/UI proof and P4 cross-build establish useful feasibility, but do not implement timers, animated drawing, uploaded sprites, production JS packages or physical JS execution. More prompt context cannot bridge missing firmware APIs.

The [release plan](16-final-platform-plan.md) selects one JavaScript SDK with existing LVGL controls, a bounded canvas, pointer input, time and packaged images. Snake, Flappy Bird, calculator, clock, stopwatch and uploaded-image whack-a-mole are independent acceptance cases, not six templates. Actual device capability selection, trusted execution feedback, durable runtime-failure recovery and stable service setup belong in the same release. Camera/microphone/speaker remain separate physically unproved extensions.

## Verified improvements and remaining limits

- Flash-Lite is selected and the service has restarted from reviewed source. One controlled task took 40.007 seconds versus Flash's 139.112 seconds with identical correct output; this is not a general speed ranking. Both had 200,000 tokens and 600 seconds. Current per-app firmware compilation time is zero.
- Reviewed media bounds are three files, 20MiB each/32MiB total; audio 60 seconds, video 30 seconds, bounded photo normalization. Fresh Android coverage of the larger limits remains open. Normalized visual input is not an embedded device asset.
- Host/native checks, the 176-test integration suite and isolated UI proofs passed within their documented scopes. The new public target build reproduction is independently accepted. Physical JS execution, native resource headroom and complete recovery still need evidence.
- The audit found that normal jobs overwrite the latest provider trace/timing, remote printed checker markers are not execution attestation, and post-active runtime failure needs a new recovery report. Existing independent backend AppSpec checks remain in place; no invalid installation is established by those findings.

## Next action

Complete independent review and public checkpoint of the revised full-chain plan. It specifies source authoring, SDK/tool freedom, actual image assets and trusted execution/repair, immutable candidate submission and durable device recovery. Official-source comparison retains managed Antigravity/Interactions as the next harness; AI Studio may help development/hosting and Pi remains a fallback. No new runtime or app capability has been deployed by this planning work.

After the planning deliverable, the next implementation milestone is the real tool bridge plus shared host/device programmable path. Its first proof uses a newly generated app from prompt/image, not a coordinator-written game. Wider requests and peripheral services have separate acceptance gates. Camera, microphone and speaker remain unavailable to generated apps until implemented/tested.

The user authorizes autonomous work and periodic public commits. Full filesystem/network permission is now enabled; direct Git/GitHub operations passed. Verify serial/provider operations when needed instead of repeating old restriction claims. Preserve the live demo during planning; no new key, hotspot credential, prompt, image or flash is needed now.
