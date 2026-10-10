# Project status

Updated: 10 October 2026, 16:28 Europe/Zurich. **The working demonstration is preserved while the user-requested programmable platform is being developed.** Read [handoff](09-session-handoff.md), [decisions](10-decisions.md), [readiness](11-readiness.md) and [work ledger](12-work-ledger.md) before resuming.

## What works on the physical device

- Android voice → Gradium → managed Gemini tools → exact package activation → user-confirmed15-second game. Sequence6, Rocket Tata, also restored and played after ordinary reboot. Requested Rocket Tap was misrecognized; transcript/title fidelity is not perfect.
- A distinct photo-only request produced sequence7, Star Tap. Its title/screens reflected the uploaded photograph of an AI-generated sketch; the user confirms the app works. The10-second duration was a default, not evidence of a20-second spoken request. No audio accompanied that image.
- Display/touch, built-in game, downloaded Focus Timer and authenticated HTTPS through the Android hotspot work. Certificate verification remains enabled. The previous event Wi-Fi had a captive portal.
- Latest public GitHub checkpoint is verified: [4d465e9](https://github.com/VincenzoImp/sketch-to-device/commit/4d465e922b542404a6429e35d8c6532035f660ad), 144 audited files, with the initial commit preserved.

## Current priority

The user wants real application programming, including flexible behavior and visuals, online research and eventually generated assets and useful device peripherals. A simple demo does not restrict the platform to predetermined games. Pragmatism is explicit: do not destabilize the working path or pursue difficult integrations without a small feasibility proof.

[Programmable apps](15-programmable-apps.md) records the comparison and selected QuickJS-NG0.14.0 experiment on the existing IDF5.5.5 stack. It also covers app lifecycle, shell aesthetics, recovery, asset/device APIs and the agent SDK. The earlier fixed-DSL/no-generated-code decision is superseded as the final direction; the current AppSpec remains the deployed baseline.

## Local source changes and evidence limits

- Runtime0.2button colors: host/native tests, independent review and actual ESP32-P4 linking passed. The new binary is not flashed; the last confirmed device runtime remains0.1.
- Media source limits: up to3files,20MiB each/32MiB total; audio60seconds, video30seconds; bounded photo normalization to2048pixels with orientation/metadata handling and transparent drawings composited over white.11real-media tests passed, including an independently reviewed transparency fix. The running service has not adopted all source changes.
- Provider diagnostics and private phase timings are independently reviewed. Corrected quoted-title handling and repair cancellation defects; generic validity does not prove intent fidelity.
- Consultable managed-agent SDK/skills and targeted documentation lookup are implemented in source. Managed Google Search and URL context are declared; live verification is pending. Image-generation integration remains a researched proposal with no device sprite renderer.
- QuickJS source is verified. Actual host engine/UI tests and an isolated engine-only P4 cross-build passed; production graphical integration and physical execution remain unproved. See the [probe](../firmware/probes/quickjs/README.md).
- The 16:15 host suite passed 176 tests; separately executed public UI probe checks also passed. An audited incremental commit/push helper is independently reviewed. The reviewed source was published as 4d465e9; later edits need a new checkpoint.

Two later Hello World color submissions failed during provider processing and left Star Tap active. The specific failure cause is unproved; missing color support alone does not explain a provider error. Local improvements have not yet been retested through a new live phone request.

## Still to complete

Continue from the passed model comparison and host engine/UI gates: coherently activate the selected Flash-Lite source and review the isolated compiled target UI adapter before physical execution. Preserve the live service/hotspot/current app. Fresh combined photo+voice, broader request/reference fidelity, physical interrupted-install recovery, repeated end-to-end runs, rehearsal and onsite submission remain open. Camera, microphone and speaker access by generated apps still requires implementation and physical verification. Accurate synchronized time, battery operation and a complete general app library are not established.

The user authorizes implementation, necessary setup, reversible probes and periodic public commits. This managed session still has read-only Git metadata and restricted network/serial access; use the normal Terminal only for concretely unavailable operations. No new key, hotspot credential or product-scope question is needed. The17:00 ready-by target remains a scheduling input; latest user steering explicitly allows worthwhile correction while considering remaining time.

The latest speed correction gives the managed agent a concise first brief, consultable references, early execution, 200,000 tokens per interaction and up to 600 seconds with progress-aware repair instead of a three-attempt ceiling. Local tests passed; the fixed-input comparison passed the same exact color-cycle behavior with Flash-Lite in40.007seconds and Flash in139.112seconds. The new source default is Flash-Lite, with broader request quality still to establish. These defaults are source changes, not a restart of the working service. The isolated real QuickJS/LVGL UI proof also passed host review; its public reproduction wrapper passed independent review and execution, while physical integration remains open.
