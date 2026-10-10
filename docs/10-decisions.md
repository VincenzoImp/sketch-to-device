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
| D14 | **Required ready-by target:** 17:00 on event day | Latest user instruction supersedes the initial 19:30 technical deadline; public competition opt-in remains distinct | [Event](01-event.md); recompute remaining time and never merge these deadlines |
| D15 | **Selected device network:** user-provided Android cellular hotspot, replacing event Wi-Fi | Event captive portal confirmed. Supplied credentials were stored privately and compiled/flashed at 14:31. Initial disconnection cleared after hotspot settings changed; at 14:34 actual device HTTPS and exact Focus Timer active ACK passed | [Readiness](11-readiness.md); preserve credentials and working hotspot. The 14:27 flash still used old Wi-Fi and was not a hotspot test; no further network choice is pending |
| D16 | **Required:** independently review every deliverable and repair/test until acceptance passes | User emphasized real practical proof, careful work, simplicity and measured optimization | [Quality gates](13-quality-gates.md); mocks or superficial green tests cannot certify real integrations |
| D17 | **Required:** autonomous work includes active research and changing unsupported hypotheses | User explicitly requested online/documentation research, questions when needed and avoiding tunnel vision | [Working method](14-autonomy-and-research.md); seek evidence that changes a concrete next action |
| D18 | **Required:** implementation and practical integration probes may begin now | User expanded context work to building/testing toward the full physical happy path; prioritize limited time | [Pipeline](05-execution-plan.md), [ledger](12-work-ledger.md); no second kickoff approval required |
| D19 | **Required:** maintain an adaptive plan verified against actual code and practical tests | Latest user stressed tracking, correctness and implementation truth over written claims | [Quality gates](13-quality-gates.md), [ledger](12-work-ledger.md); reopen affected claims when code or evidence changes |
| D20 | **Required design latitude:** treat the original idea/hints as a starting point and improve them where useful | User explicitly grants freedom to choose better implementation/product details; preserve the core one-shot physical outcome and verify choices | [Product](02-product.md), [pipeline](05-execution-plan.md); change decisions from evidence, not speculative expansion |
| D21 | **Proposed extension:** generated apps may call AI during use through the backend | User asked about feasibility and useful agent context; coordinator retains this as P1 after the physical happy path, not a new prerequisite | [Product](02-product.md); v1 has no AI/network action, provider keys remain server-side |
| D22 | **Required product expansion:** real app programming and broad device features, with consultable skills/SDK and minimal artificial constraints | User explicitly rejected treating the initial DSL as the final scope and asked for primary-source research | [Programmable platform](15-programmable-apps.md); supersedes the earlier blanket no-generated-code rule and MVP feature freeze, while retaining resource protection and recovery |
| D23 | **Selected experiment:** official QuickJS-NG0.14.0 on the existing IDF5.5.5 stack | Comparison considered Lua, WASMachine, MicroPython, Brookesia and native firmware; JavaScript fits an event-driven SDK without requiring a full IDF migration | [Programmable platform](15-programmable-apps.md); host/P4 feasibility and measured resource gates precede production integration; Lua remains a fallback |
| D24 | **Required:** periodic public commits with real history | User repeated this requirement, including short messages; initial commit alone is insufficient | [Readiness](11-readiness.md); reviewed incremental publisher is prepared, but managed Git/network restrictions still prevent direct push |
| D25 | **Selected UI direction:** system-owned app library/exit/recovery with flexible app layout and styling | User asked to revisit the base device framework aesthetically and practically alongside generation | [Programmable platform](15-programmable-apps.md); proposed lifecycle/safe-area design must be implemented and tested, not just skinned |


The implemented path has two distinct generated physical apps and ordinary reboot evidence for the first. Broader request fidelity, combined media, fault recovery and the programmable extension remain open. The [ledger](12-work-ledger.md) records exact evidence and remaining gates.

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

## Fallback semantics

Photo plus speech is a declared fallback for video transport/decoding failure and preserves visual-plus-spoken understanding. Text plus app-specific Gradium TTS is an **unimplemented alternative** that could demonstrate both partners, but does **not** fulfill the planned multimodal-input acceptance. It remains a reduced outcome unless the user accepts that scope change and it is implemented and tested. A simulator or saved package similarly cannot satisfy live generation on physical hardware.

## Change procedure

When scope or a technical choice changes, add its origin, reason and affected acceptance gate here; edit the owning document; then reconcile [status](00-status.md), [handoff](09-session-handoff.md) and [work ledger](12-work-ledger.md). Notify workers of the new contract revision before they continue. Do not fork a second schema or silently weaken acceptance to make a test pass.
