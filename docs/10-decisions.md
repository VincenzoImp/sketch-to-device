# Decision register

This register preserves why the project has its current shape without copying chat transcripts. Detailed behavior belongs to each linked owning document. Latest explicit user instructions override a prior proposal.

Status meanings: **required** is an explicit user constraint; **selected** is the current working design/default; **proposed** awaits the relevant feasibility gate; **validated** requires a recorded successful test; **superseded** remains historical only. Selected does not mean tested or personally chosen by the user.

## Requirements and current choices

| ID | Decision and status | Origin and rationale | Owning document and revisit condition |
| --- | --- | --- | --- |
| D01 | **Required:** one prompt produces a working app on the physical device | User clarified that generation itself is the demo; a game or simple app is acceptable | [Product](02-product.md); change only on user steering |
| D02 | **Required:** all project artifacts and demo content in English | User explicitly required English except direct conversation in this chat | [AGENTS.md](../AGENTS.md); applies to worker handoffs too |
| D03 | **Required:** Google DeepMind + Gradium used substantively | User requested at least two partners and selected this pair | [Partners](research/partners.md); both performed actual work in the first voice-generated physical app. Visual repeat and remaining acceptance/fidelity checks stay open |
| D04 | **Required target:** confirmed Waveshare model and Android phone | User confirmed board, camera, battery and phone platform | [Readiness](11-readiness.md); chip identified and display/touch/built-in tap app reported working; camera and battery operation untested |
| D05 | **Selected:** one Generate and install action after pairing | Design interpretation of D01; avoids a required multi-turn/approval sequence for reversible packages | [Contracts](04-contracts.md); pairing is setup, not a demo interruption |
| D06 | **Selected:** mobile web companion | Implementation choice to avoid app-store distribution; user specified a phone companion, not a mandatory native app | [Architecture](03-architecture.md); change only if real Android/media tests justify it |
| D07 | **Selected and implemented:** ESP-IDF/LVGL runtime with declarative AppSpec | Allows generated interactive apps within known capabilities without a new firmware build for every request | [Contracts](04-contracts.md); fixture and generated app exact ACKs, physical controls and generated-app ordinary reboot passed. Photo-only Star Tap also passed exact ACK and user-confirmed controls; interrupted-install recovery remains open |
| D08 | **Selected and implemented:** managed Gemini generation with inline images, Gradium transcripts and trusted host validators | Official inline-image support and actual managed execution/artifact evidence allow one agent path without an extra model prepass | [Architecture](03-architecture.md); first voice-generated physical run passed, but requested title changed. Production used generic checks; strict 15-second behavior passed independently afterward. A separate photo-only app now passes; fresh combined photo+voice remains to prove |
| D09 | **Selected default:** spoken English input through Gradium STT | User accepted English; makes the second partner visible in a useful role | [Product](02-product.md); fixed runtime_context followed measured A/B and review. First physical run still misrecognized title/tap/duration tokens; no general accuracy or strict-production-check claim |
| D10 | **Proposed candidate:** ten-second Tap Sprint game | Demonstrates local timer, state, navigation and touch using a small runtime | [Product](02-product.md); not a user-mandated final app and not a hardcoded generation result |
| D11 | **Selected:** backend-mediated HTTPS polling | Avoids browser Bluetooth and direct phone-to-board addressing | [Architecture](03-architecture.md); actual hotspot HTTPS and exact fixture/generated ACKs passed, including after coordinated endpoint change. Preserve working service/endpoint for the visual repeat |
| D12 | **Required:** solo human builder supported by subagents and review loops | User works alone and authorized delegation, setup and necessary installs | [AGENTS.md](../AGENTS.md), [pipeline](05-execution-plan.md); agent limits depend on session capability |
| D13 | **Required:** sanitized public GitHub repository | User explicitly requested public publication; credentials and original PDFs remain private | [Readiness](11-readiness.md); publication authorization persists across sessions |
| D14 | **Earlier ready-by target:** 17:00 on event day | Earlier scheduling input; the later platform correction and D30 implementation goal govern current work, without evidence of completion by that time; public competition opt-in remains distinct | [Event](01-event.md); recompute remaining time and never merge these deadlines |
| D15 | **Selected device network:** user-provided Android cellular hotspot, replacing event Wi-Fi | Event captive portal confirmed. Supplied credentials were stored privately and compiled/flashed at 14:31. Initial disconnection cleared after hotspot settings changed; at 14:34 actual device HTTPS and exact Focus Timer active ACK passed | [Readiness](11-readiness.md); preserve credentials and working hotspot. The 14:27 flash still used old Wi-Fi and was not a hotspot test; no further network choice is pending |
| D16 | **Required:** independently review every deliverable and repair/test until acceptance passes | User emphasized real practical proof, careful work, simplicity and measured optimization | [Quality gates](13-quality-gates.md); mocks or superficial green tests cannot certify real integrations |
| D17 | **Required:** autonomous work includes active research and changing unsupported hypotheses | User explicitly requested online/documentation research, questions when needed and avoiding tunnel vision | [Working method](14-autonomy-and-research.md); seek evidence that changes a concrete next action |
| D18 | **Durable authorization, current phase governed by D30:** implementation and practical integration probes | User expanded context work to building/testing; the latest active goal resumes the reviewed implementation | [Pipeline](05-execution-plan.md), [ledger](12-work-ledger.md); no second kickoff approval required |
| D19 | **Required:** maintain an adaptive plan verified against actual code and practical tests | Latest user stressed tracking, correctness and implementation truth over written claims | [Quality gates](13-quality-gates.md), [ledger](12-work-ledger.md); reopen affected claims when code or evidence changes |
| D20 | **Required design latitude:** treat the original idea/hints as a starting point and improve them where useful | User explicitly grants freedom to choose better implementation/product details; preserve the core one-shot physical outcome and verify choices | [Product](02-product.md), [pipeline](05-execution-plan.md); change decisions from evidence, not speculative expansion |
| D21 | **Proposed extension:** generated apps may call AI during use through the backend | User asked about feasibility and useful agent context; coordinator retains this as P1 after the physical happy path, not a new prerequisite | [Product](02-product.md); v1 has no AI/network action, provider keys remain server-side |
| D22 | **Required product expansion:** real app programming and broad device features, with consultable skills/SDK and minimal artificial constraints | User explicitly rejected treating the initial DSL as the final scope and asked for primary-source research | [Programmable platform](15-programmable-apps.md); supersedes the earlier blanket no-generated-code rule and MVP feature freeze, while retaining resource protection and recovery |
| D23 | **Selected experiment:** official QuickJS-NG0.14.0 on the existing IDF5.5.5 stack | Comparison considered Lua, WASMachine, MicroPython, Brookesia and native firmware; JavaScript fits an event-driven SDK without requiring a full IDF migration | [Programmable platform](15-programmable-apps.md); host/P4 feasibility and measured resource gates precede production integration; Lua remains a fallback |
| D24 | **Required:** periodic public commits with real history | User repeated this requirement, including short messages; initial commit alone is insufficient | [Readiness](11-readiness.md); reviewed incremental publisher directly published d223469 after full access became available; continue reviewed commits |
| D25 | **Selected UI direction:** system-owned app library/exit/recovery with flexible app layout and styling | User asked to revisit the base device framework aesthetically and practically alongside generation | [Programmable platform](15-programmable-apps.md); proposed lifecycle/safe-area design must be implemented and tested, not just skinned |
| D26 | **Required optimization objective:** minimize time to a correct app, with ample token budget and useful tool access | User explicitly prioritizes speed over token cost and proposes a fast model with freedom to run commands, research and repair | Compare supported managed models on the same request and SDK. Keep all references consultable, remove redundant mandatory reading, and measure complete successful runs rather than token throughput alone |
| D27 | **Required audit pause:** stop incremental implementation and plan one coherent programmable release | Latest user request after Flappy Bird refusal explicitly names Snake, calculator, clock, stopwatch and uploaded-image whack-a-mole as expected flexibility | [Audited release plan](16-final-platform-plan.md); preserve the working demo, resolve checker/package/lifecycle contracts first, and use all six cases plus an unseen composition as acceptance rather than templates |
| D28 | **Historical resume, clarified by D29:** prepare the platform for a concrete programmable app test and commit reviewed work | Followed the first audit; full filesystem/network access became enabled. The subsequent user correction explicitly rules out the coordinator hand-building the requested game | [Release plan](16-final-platform-plan.md); estimates are not per-app latency or fixed promises |
| D29 | **Completed planning:** redesign the full input → agent → generated program/assets → device path for broad app programming | User will supply the prompt and image and expects Gemini to author the app. Reassess all affected modules and research Google AI Studio/Pi using primary sources; app-specific code must be generated, with no prepared app/game assembly. Broad coding freedom is the objective, not a six-app whitelist | [Release plan](16-final-platform-plan.md); hold implementation/live probes during this planning deliverable, preserve the working flow, review and publish the plan. Distinguish agent tool freedom, app logic and implemented hardware services |
| D30 | **Current active goal: implement the reviewed programmable-platform redesign** | After publication at5a183fd, the user set the attached plan summary as an active goal and asked to achieve it. This resumes implementation, provider/tool probes and practical integration in the planned order; it does not imply deployed readiness | [Release plan](16-final-platform-plan.md); keep generated authorship, shared SDK, real execution/repair, recoverable installation and all applicable release gates. Preserve the current demo and publish reviewed increments |

The implemented path has voice, photo-only and text-generated physical app evidence, with ordinary reboot evidence for the first voice app. Broader request fidelity, combined media, fault recovery and the programmable extension remain open. The [ledger](12-work-ledger.md) records exact evidence and remaining gates.

## D31 — Final thirty-minute integration window

User steering at18:31Europe/Zurich: only thirty minutes remain, so prioritize the
first real programmable end-to-end path now. This changes immediate execution
priority, not the general authoring requirement. Text, image and audio remain
valid alone or in any supported combination; no prompt/image special case or
prepared app is introduced. Defer new peripheral modules and aesthetic work.
Complete essential reviewed delivery/recovery, activate the service and runtime,
then obtain fresh user-authored-input physical evidence and publish checkpoints.
Do not relabel unimplemented broader SDK features as finished because time is short.

## D32 — Preserve Penguin Tap and stabilize for a fresh user test

The latest user removes the immediate deadline and specifies this order: save the installed Penguin Tap first, commit/push all reviewed public work, fix remaining bugs, then let them repeat the end-to-end flow. The exact private package/source/firmware/database backup is complete and independently verified. Configured binaries, inputs and credentials remain private. Preserve the working app/service; Gemini must author the next user request. D32 supersedes D31's deadline priority, while retaining the broader [release plan](16-final-platform-plan.md) and its honest capability gates.

## D33 — Commit and shut down

After stabilization, the user explicitly requests committing everything and shutting down. Preserve the verified private Penguin backups and installed app storage, verify the public push, stop project services/processes and leave the project idle. Do not resume providers, probes or service startup until requested. This supersedes D32's instruction to leave the working service running. USB power and the Android hotspot are physical controls; stopping the Mac service does not power them off.

## Refinements that must not be undone accidentally

| Earlier direction | Current interpretation |
| --- | --- |
| Full conversational creation with many attachment types | Long-term direction retained; P0 accepts one request with up to three supported media attachments. Conversation, PDFs and broader format expansion remain P1/P2 |
| Required preview and a separate install click | Superseded by D05; preview is optional P1, validation remains mandatory |
| Routine/timer as the default demo | Replaced by a simple-game candidate after user clarification; exact game remains flexible |
| Possible third partner Entire | Parked; Google DeepMind + Gradium are sufficient for the user's chosen scope |
| Local context only | Superseded by authorized public GitHub publication of sanitized project files |
| Device unavailable and both keys unknown | Superseded: both minimal provider authentications passed; chip and flash identified, custom runtime flashed and built-in tap behavior reported. See readiness for specific untested capabilities |
| Separate multimodal model prepass and ConceptBrief before managed generation | Superseded by direct managed-agent images, one extracted video frame, Gradium speech and narrow trusted behavior requirements. ConceptBrief remains a deferred proposal, not an implemented gate |

## Measured model selection

Following D26, one controlled live Hello Colors task produced identical host-verified bytes with Flash-Lite in40.007seconds and Flash in139.112seconds. The coordinator selected `gemini-3.5-flash-lite` as the source default, preserving200,000tokens,600seconds and the same tools/checks. This is a pragmatic operational choice from one task; broader quality remains unproved. Service activation and the subsequent physical Hello Colors test have now passed; Flappy Bird exposed the remaining format boundary.

## Fallback semantics

Photo plus speech is a declared fallback for video transport/decoding failure and preserves visual-plus-spoken understanding. Text plus app-specific Gradium TTS is an **unimplemented alternative** that could demonstrate both partners, but does **not** fulfill the planned multimodal-input acceptance. It remains a reduced outcome unless the user accepts that scope change and it is implemented and tested. A simulator or saved package similarly cannot satisfy live generation on physical hardware.

## Change procedure

When scope or a technical choice changes, add its origin, reason and affected acceptance gate here; edit the owning document; then reconcile [status](00-status.md), [handoff](09-session-handoff.md) and [work ledger](12-work-ledger.md). Notify workers of the new contract revision before they continue. Do not fork a second schema or silently weaken acceptance to make a test pass.
