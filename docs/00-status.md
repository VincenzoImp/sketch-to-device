# Project status

Updated: 10 October 2026, 15:50 Europe/Zurich. **The working demonstration is preserved while the user-requested programmable platform is being developed.** Read [handoff](09-session-handoff.md), [decisions](10-decisions.md), [readiness](11-readiness.md) and [work ledger](12-work-ledger.md) before resuming.

## What works on the physical device

- Android voice → Gradium → managed Gemini tools → exact package activation → user-confirmed15-second game. Sequence6, Rocket Tata, also restored and played after ordinary reboot. Requested Rocket Tap was misrecognized; transcript/title fidelity is not perfect.
- A distinct photo-only request produced sequence7, Star Tap. Its title/screens reflected the uploaded photograph of an AI-generated sketch; the user confirms the app works. The10-second duration was a default, not evidence of a20-second spoken request. No audio accompanied that image.
- Display/touch, built-in game, downloaded Focus Timer and authenticated HTTPS through the Android hotspot work. Certificate verification remains enabled. The previous event Wi-Fi had a captive portal.
- Initial public GitHub publication is verified: [VincenzoImp/sketch-to-device](https://github.com/VincenzoImp/sketch-to-device), commit8826f2edb8ab662cc2e524e4867661832c8d04cd,100audited files.

## Current priority

The user wants real application programming, including flexible behavior and visuals, online research and eventually generated assets and useful device peripherals. A simple demo does not restrict the platform to predetermined games. Pragmatism is explicit: do not destabilize the working path or pursue difficult integrations without a small feasibility proof.

[Programmable apps](15-programmable-apps.md) records the comparison and selected QuickJS-NG0.14.0 experiment on the existing IDF5.5.5 stack. It also covers app lifecycle, shell aesthetics, recovery, asset/device APIs and the agent SDK. The earlier fixed-DSL/no-generated-code decision is superseded as the final direction; the current AppSpec remains the deployed baseline.

## Local source changes and evidence limits

- Runtime0.2button colors: host/native tests, independent review and actual ESP32-P4 linking passed. The new binary is not flashed; the last confirmed device runtime remains0.1.
- Media source limits: up to3files,20MiB each/32MiB total; audio60seconds, video30seconds; bounded photo normalization to2048pixels with orientation/metadata handling and transparent drawings composited over white.11real-media tests passed, including an independently reviewed transparency fix. The running service has not adopted all source changes.
- Provider diagnostics and private phase timings are independently reviewed. Corrected quoted-title handling and repair cancellation defects; generic validity does not prove intent fidelity.
- Consultable managed-agent SDK/skills and targeted documentation lookup are implemented in source. Managed Google Search and URL context are declared; live verification is pending. Image-generation integration remains a researched proposal with no device sprite renderer.
- QuickJS source is verified. Actual host engine tests and an isolated P4 cross-build passed; graphical integration and physical execution remain unproved. See the [probe](../firmware/probes/quickjs/README.md).
- The full host suite passes162tests. An audited incremental commit/push helper is independently reviewed. New local edits are not yet a verified public commit.

Two later Hello World color submissions failed during provider processing and left Star Tap active. The specific failure cause is unproved; missing color support alone does not explain a provider error. Local improvements have not yet been retested through a new live phone request.

## Still to complete

Pass the isolated engine and SDK gates, then decide the next integration from measured evidence. Preserve the live service/hotspot/current app. Fresh combined photo+voice, broader request/reference fidelity, physical interrupted-install recovery, repeated end-to-end runs, rehearsal and onsite submission remain open. Camera, microphone and speaker access by generated apps still requires implementation and physical verification. Accurate synchronized time, battery operation and a complete general app library are not established.

The user authorizes implementation, necessary setup, reversible probes and periodic public commits. This managed session still has read-only Git metadata and restricted network/serial access; use the normal Terminal only for concretely unavailable operations. No new key, hotspot credential or product-scope question is needed. The17:00 ready-by target remains a scheduling input; latest user steering explicitly allows worthwhile correction while considering remaining time.
