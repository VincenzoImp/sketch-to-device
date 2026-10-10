# Project status

Updated: 10 October 2026, 16:52 Europe/Zurich. **Implementation and physical probes are paused for the user-requested whole-project audit and coherent release plan.** The working demo remains intact. Read [the new plan](16-final-platform-plan.md), [handoff](09-session-handoff.md), [readiness](11-readiness.md) and [work ledger](12-work-ledger.md) before resuming.

## What works

- Android voice → Gradium → managed Gemini tools → exact package activation → user-confirmed 15-second game. Sequence6 Rocket Tata also restored after an ordinary reboot. The requested title Rocket Tap was mistranscribed.
- A separate photo-only request generated sequence7 Star Tap and worked physically. Its 10-second duration was a default; there was no accompanying audio. This is not combined photo/voice evidence.
- After the service restart and runtime0.2 flash, fresh Hello Colors sequence12 passed exact activation, independent initial-state/six-press checks and user-confirmed physical color cycling. The next Flappy Bird request returned `unsupported_request` and preserved Hello Colors.
- Display/touch, downloaded apps and authenticated HTTPS through the Android cellular hotspot work. Certificate verification stays enabled. The event Wi-Fi had a captive portal.
- Latest verified public checkpoint: [35e8d69](https://github.com/VincenzoImp/sketch-to-device/commit/35e8d69267ff5fea5b7c85cfbf0ced2813c72fb9), 144 audited files with earlier history preserved. Later local work needs a new publication checkpoint.

## Audit conclusion

The product currently generates a fixed JSON AppSpec, not general programs. The isolated QuickJS host/UI proof and P4 cross-build establish useful feasibility, but do not implement timers, animated drawing, uploaded sprites, production JS packages or physical JS execution. More prompt context cannot bridge missing firmware APIs.

The [release plan](16-final-platform-plan.md) selects one JavaScript SDK with existing LVGL controls, a bounded canvas, pointer input, time and packaged images. Snake, Flappy Bird, calculator, clock, stopwatch and uploaded-image whack-a-mole are independent acceptance cases, not six templates. Actual device capability selection, trusted execution feedback, durable runtime-failure recovery and stable service setup belong in the same release. Camera/microphone/speaker remain separate physically unproved extensions.

## Verified improvements and remaining limits

- Flash-Lite is selected and the service has restarted from reviewed source. One controlled task took 40.007 seconds versus Flash's 139.112 seconds with identical correct output; this is not a general speed ranking. Both had 200,000 tokens and 600 seconds. Current per-app firmware compilation time is zero.
- Reviewed media bounds are three files, 20MiB each/32MiB total; audio 60 seconds, video 30 seconds, bounded photo normalization. Fresh Android coverage of the larger limits remains open. Normalized visual input is not an embedded device asset.
- Host/native checks, the 176-test integration suite and isolated UI proofs passed within their documented scopes. The new public target build reproduction is independently accepted. Physical JS execution, native resource headroom and complete recovery still need evidence.
- The audit found that normal jobs overwrite the latest provider trace/timing, remote printed checker markers are not execution attestation, and post-active runtime failure needs a new recovery report. Existing independent backend AppSpec checks remain in place; no invalid installation is established by those findings.

## Next action

The hardware, agent and final cold-start reviews accepted the reconciled plan. The public context check passed 158 files and the diff whitespace check passed. The reviewed checkpoint is ready; publication through the restricted Git/network boundary remains pending. Subsequent implementation begins with milestone0: freeze shared contracts and prove an actual same-engine testing tool route, before building the production script path. The partial ignored physical-flash helper is parked and unreviewed; do not run it. No fresh user generation, service restart or flash is needed for this audit.

Combined photo+voice, wider request/reference fidelity, interrupted installation, repeated runs, rehearsal and onsite submission are still open. The hardware integration estimate alone is 11–22 focused engineer-hours, with backend broker/hosting work not yet sized. The old17:00 target is not evidence that this can be completed by then. Preserve the demonstrated flow while planning honestly.

The user authorizes autonomous work and periodic public commits. This managed session still has read-only Git metadata and restricted network/serial access; only concretely unavailable operations require the normal Terminal. No new key, hotspot credential or product-scope question is needed.
