# Project status

Updated: 10 October 2026, 14:54 Europe/Zurich. Status: the first complete Android voice → Gradium → Gemini tools → physical generated app run passed, with a title-fidelity limitation. Sequence 6 rocket_tata received an exact active ACK; the user confirms the 15-second game, restart controls, phone confirmation and restoration/play after ordinary reboot. Requested Rocket Tap became Rocket Tata. Production ran generic checks because narrow speech extraction returned false/null; independent strict 15-second checks passed afterward. A second visual/voice STAR TAP request is being prepared, with no new job or second generated result yet. Overall acceptance remains open. New sessions start with [the handoff](09-session-handoff.md). [Decisions](10-decisions.md), [readiness](11-readiness.md) and [work ledger](12-work-ledger.md) own detailed evidence.

## Confirmed by the user

- Device: **Waveshare ESP32-P4-WIFI6-Touch-LCD-3.5**, with camera and battery available.
- Companion target: **Android phone**.
- Demo and every project artifact, document, interface, prompt and code comment must be **English**. Conversation with the user may remain Italian.
- Main demo: a **single prompt in the companion creates a working app on the device**. A simple app or game is acceptable.
- Partner preference: **Gradium + Google DeepMind**. At least two partners must have meaningful, observable roles.
- The hackathon priority is a feasible, complete, simple and linear path.
- Research partner documentation and prepare a controlled implementation pipeline with subagents and bounded repair loops.
- User-specified technical delivery deadline: **17:00 on 10 October**, superseding the earlier 19:30 target.
- The user is the only human participant and authorizes the assistant to install and configure necessary tools autonomously.
- A public GitHub repository is requested. Publication of sanitized project files is authorized; original PDFs and secrets remain private.
- The device has been connected to the Mac. After confirming the event Wi-Fi captive portal, the user supplied Android hotspot credentials. They are stored privately and included in the latest flashed firmware; the hotspot now supports actual device HTTPS and an exact active fixture ACK.
- Both Gemini and Gradium API keys have been supplied and stored privately. Subsequent probe evidence is recorded below; no new key request is justified without diagnosis.
- Work autonomously toward the complete happy path; keep the plan adaptive, pragmatic and tracked. Code and practical tests establish what is implemented. Research unfamiliar or contradictory behavior before committing to a path; see [the working method](14-autonomy-and-research.md).
- Every deliverable must receive independent review, material fixes and meaningful verification; end-to-end functionality must be tested on the actual phone, providers and device. See [quality gates](13-quality-gates.md).

## Decisions and proposals

| Decision | Status | Reason |
| --- | --- | --- |
| Google DeepMind + Gradium | Both performed actual work in the first complete voice-generated physical run | Requested title was misrecognized; visual repeat, broader fidelity and remaining acceptance checks stay open |
| ESP-IDF + LVGL firmware with JSON AppSpec | Fixture followed by one generated package, exact ACK, physical controls and ordinary reboot passed | Second generated/visual run and interrupted-install recovery remain to prove |
| Mobile web companion on Android | Fresh audio submission reached physical generated activation and phone confirmation | Earlier three failures remain historical; next sketch-plus-voice request has not arrived |
| One Generate and install action on a paired device | Selected interpretation of the required one-shot outcome | Authorizes deployment of a validated, reversible app package |
| English input, interface and demo | Confirmed | Shared language across demo, partners and generated apps |
| Short video, or sketch photo with speech | Actual voice-only physical run passed with title limitation | User is preparing STAR TAP sketch/voice; visual input is not yet proved |
| 10-second tap game | Candidate | Start, score, timer and result fit a small declarative runtime |
| One device and one demo user | Selected and implemented scope | Keeps pairing and synchronization manageable |
| Chat revisions and preview interaction | P1 | Useful later; not required in the main demo |

The [canonical contract](04-contracts.md) sets product limits independently of provider limits. Recording guidance is 15–30 seconds; shorter clips are accepted and the hard maximum is 30 seconds. Decision provenance and superseded assumptions are in [the decision register](10-decisions.md).

## Remaining work and dependencies

The [readiness register](11-readiness.md) separates user-only actions from assistant-owned probes and environment restrictions. No further product explanation, provider key, board model, phone platform, language, team-size or installation permission is needed now.

The next work is operational: receive the new sketch-plus-voice request for a 20-second STAR TAP game and observe a distinct generated deployment. The user clarified that the earlier App installed reply referred to Rocket Tata; no second input/result exists yet. A second 600-second observer began around 14:52, excluding four prior phone jobs. Keep the working service, endpoint, hotspot and source unchanged unless a concrete failure justifies a fix. Verify visual influence, requested title/duration, exact ACK and physical behavior, then remaining negative/recovery/rehearsal checks. Public publication and onsite submission are outstanding.

## Observed local inventory

The board is confirmed as ESP32-P4 revision 3.2 with 16 MB flash; the original backup is verified. The hotspot resolved usable device access after the event captive-portal/TLS issue. Focus Timer fixture controls passed, followed by generated sequence 6 rocket_tata with all four delivery ACK stages. The user confirms Start, taps through the 15-second round, final score, Play again resetting score/countdown and phone installation confirmation. An ordinary reboot without flashing restored the same app and a new game started. Certificate verification remains enabled; interrupted-install and power-loss behavior remain separate unproved physical cases.

Earlier text generations and preserved-audio replays have distinct archived hashes and limitations. The new phone job first appeared at 12:47:16 UTC and reached exact active ACK at 12:48:46 UTC: 90.598 seconds by observer timing. Gemini completed with two execution pairs and 24,026 effective tokens. The served app is 1,307 bytes; source and publication hashes are separately recorded in the ledger. STT misrecognized Rocket Tap as Rocket Tata and used 15th/top, so production extracted tap_game=false/duration=null and used generic checks. Independent post-install checks passed the strict five-checkpoint 15-second scenario, additional host cases and actual served-byte C parsing under ASan/UBSan. These later checks must not be described as production checks for that job. Full transcript accuracy is not claimed.

Node, FFmpeg, cloudflared and GitHub CLI are installed; GitHub browser authentication succeeded. No repository has been published. Earlier text-generation failures have no confirmed cause; the later successful text runs do not establish a retrospective diagnosis. Firmware partition and backup-timeout defects were corrected and verified.

The managed session still cannot resolve provider/tunnel hosts, bind a local server, initialize `.git`, or use serial read/write. A direct retry at 13:22 confirmed serial denial and DNS failure. Run all permitted compilation, code inspection and host checks here; use the normal Terminal only for operations requiring unavailable access. These restrictions do not invalidate successful user-terminal provider probes.

Provider keys stay in ignored `.env`, mode 0600. Do not print them or copy them into public artifacts. The hotspot has actual device HTTPS and exact active ACKs for the fixture and first generated app.

## Verification record

| Check | Result |
| --- | --- |
| Four supplied PDFs | Read; credentials were not copied into public context |
| Public event and schedule | Located on Luma; see [event notes](01-event.md) |
| Device and partner documentation | Researched; sources are in the research documents |
| Exact device, Android and English demo | Confirmed by the user |
| Device USB connection | [ROM query identified ESP32-P4 revision 3.2 with 16 MB flash](research/hardware-probe.md); user reports working display/touch and custom built-in tap app. Camera and battery operation remain unverified |
| Private provider configuration | Both Gemini and Gradium keys present; values omitted |
| Provider access probes | Managed session: DNS blocked. User's normal terminal: Gradium HTTP 200/authenticated/credits available; simplified Gemini request HTTP 200/completed/expected reply. [Evidence](research/provider-probe.md) |
| Managed execution and artifact download | External-terminal probe passed at 12:51:59 local: one actual execution, exact downloaded bytes/hash, 20.582 seconds; [evidence](research/managed-probe.md) |
| Companion/service slice | Accepted source loaded; fresh Android audio reached actual generated active ACK and user-confirmed phone success. Service/endpoint/flash setup is complete and source frozen |
| AppSpec host foundation | [Code and fixtures exist](../contracts/README.md); independent review and final check evidence in the work ledger |
| Public GitHub repository | Requested and authorized; no creation or push completed |
| Hardware build and flash | Original backup and physical fixture checks passed. Latest endpoint-configured runtime flash completed; 1,449,072-byte binary and private/header/object configuration checks independently verified |
| Known-package delivery | Focus Timer fixture exact ACK and physical controls passed before generated sequence 6 replaced it; keep fixture evidence distinct from AI output |
| Phone → providers → device | First voice-generated physical game passed exact ACK, controls and ordinary reboot, with title-fidelity limitation. 90.598 seconds from observer first-seen; visual/voice repeat still pending |
| Latest host suite | 131 tests passed at 14:37:53. Later actual served-app strict host checks and native C ASan/UBSan parsing passed independently; physical behavior/reboot are user-confirmed |
| Independent document review | Coordinator accepted the 14:47 reconciliation. This 14:54 milestone update is released for coordinator review |
| Fresh-session reconstruction | Agent without chat history recovered intent; continuity findings incorporated into linked registers |
| Public context audit | Guard regression tests passed; final source snapshot pending the active changes and review |

When a decision changes, record why here and update its owning document. Repetition does not turn a proposal into a verified fact.
