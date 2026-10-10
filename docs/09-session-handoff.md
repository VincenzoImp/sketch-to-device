# Start here when resuming the project

This is the entry point for a session that has no conversation history. Read [AGENTS.md](../AGENTS.md), this page and [current status](00-status.md), then follow the role map below. Do not ingest the whole archive or private PDFs by default.

## Intent in one minute

The user is a solo participant in the 10 October 2026 Agentic AI Hack Zürich. They want a convincing, feasible **one-shot creation demo**: one English concept submitted from an Android companion becomes an interactive app on their Waveshare ESP32-P4-WIFI6-Touch-LCD-3.5. Google DeepMind and Gradium must perform observable work. The camera and battery are present; initial input comes from the phone.

The selected implementation is a stable ESP-IDF/LVGL firmware that runs bounded JSON AppSpec packages. The managed Gemini agent interprets the concept and builds/tests the package; Gradium processes the spoken request. The selected paired device receives the checked package automatically under one Generate and install action. The candidate tap game demonstrates real behavior; a bring-up fixture must not replace generation in the final demo.

The user originally described a rich chat with video, audio, text and attachments, then emphasized a simple one-shot demonstration. Preserve the wider product direction, but conversation revisions, PDFs, app libraries, interactive previews and on-device media capture are later work. See [product scope](02-product.md) and [decision history](10-decisions.md).

## What is happening now

**Active phase at 14:54: visual/voice repeat after the first complete voice-generated physical run; ready-by target 17:00.** Fresh Android audio passed Gradium, managed Gemini tools, artifact/host validation and exact active ACK for sequence 6 rocket_tata. The user confirmed the 15-second game, Play again reset, phone confirmation and ordinary reboot restoration. Requested Rocket Tap became Rocket Tata; transcript extraction selected generic checks, while stricter intended-game checks passed independently afterward. Source is frozen. The user is preparing a 20-second STAR TAP sketch-plus-voice request; the new observer is active but no second job/result exists yet.

Public research and operating documents exist. Read the [work ledger](12-work-ledger.md) for current code and probe ownership. Firmware C runtime/LVGL renderer, backend HTTP/deployment/generation and companion are implemented as independently reviewed slices. Actual integration tests are underway; none of these alone establishes the complete product. Support scripts and headless reference behavior do not establish provider or physical device success.

Current evidence on 10 October: board/backup/setup, fixture delivery, one generated physical app and ordinary reboot restoration passed. Working Android hotspot, service and endpoint are already configured. The first generated ACK took 90.598 seconds from observer first-seen; provider completed with two execution pairs and 24,026 effective tokens. Source and served hashes differ by publication serialization and are recorded separately. Production measured requirements were false/null; strict 15-second host behavior checks passed independently after installation, and a separate native C check verified parsing only. These results do not rewrite the production-check history. Title and full transcript fidelity remain limited. No visual generation or second generated app is established; GitHub publication is unverified. The [readiness register](11-readiness.md) owns remaining conditions.

## Next actions in the current phase

1. Read [work ledger](12-work-ledger.md), check active ownership, and continue the first incomplete item within the latest user request. Do not redo completed research without a concrete gap.
2. Preserve the public context audit and archive after document edits. Resolve the authenticated GitHub publishing route if available; publication is already authorized, but no remote repository has been verified.
3. Continue the incomplete gates in the [execution pipeline](05-execution-plan.md): observe the requested STAR TAP sketch/voice submission as a new job, then verify actual visual influence, 20-second duration/title, new exact ACK and physical controls. The second 600-second observer started around 14:52 and excludes four prior phone jobs; the earlier observer ended and is archived. The user clarified the prior App installed message referred to Rocket Tata, not a second app. Setup and ordinary reboot are complete; do not repeat them as unfinished tasks. Finish remaining negative/recovery/rehearsal and publication gates, preserving source freeze unless new evidence warrants a fix.

The stated event deadlines belong to **10 October 2026, Europe/Zurich**. A later session must check the current date/time and user objective. Do not reuse an expired same-day schedule as though hours remain.

## Read by responsibility

| Role or question | Required documents | Expected next output |
| --- | --- | --- |
| Coordinator | [Product](02-product.md), [decisions](10-decisions.md), [readiness](11-readiness.md), [work ledger](12-work-ledger.md), [pipeline](05-execution-plan.md) | Current scope, owner assignments, unblock actions and gate evidence |
| Hardware worker | [Architecture](03-architecture.md), [contracts](04-contracts.md), [hardware research](research/hardware.md), [acceptance](06-validation-demo.md) | Identified board/revision, working BSP, interpreter and exact install ACK |
| Backend worker | [Contracts](04-contracts.md), [Gemini](research/gemini.md), [partners](research/partners.md), [acceptance](06-validation-demo.md) | Real provider calls, trusted validation and reliable package delivery |
| Companion worker | [Product](02-product.md), [architecture](03-architecture.md), [contracts](04-contracts.md), [acceptance](06-validation-demo.md) | Android input, one-action generation and truthful device state |
| Reviewer | The assigned gate's documents, [acceptance](06-validation-demo.md), actual changed files and evidence | Reproducible material defects and limits of checks performed |
| Pitch and submission | [Event](01-event.md), [product](02-product.md), [demo](06-validation-demo.md) | English pitch using only working capabilities and actual partner evidence |

## Which file owns which answer

- [AGENTS.md](../AGENTS.md): working instructions and durable authorization.
- [Status](00-status.md): concise current snapshot, pointing to canonical registers.
- [Product](02-product.md): intended user experience, P0/P1/P2 and completion scope.
- [Architecture](03-architecture.md): component responsibilities and transport design.
- [Contracts](04-contracts.md): authoritative limits, field names and runtime semantics.
- [Pipeline](05-execution-plan.md): gate definitions and repair strategy; [work ledger](12-work-ledger.md): actual gate state and owner.
- [Decisions](10-decisions.md): origin, rationale and decision status; [readiness](11-readiness.md): access, physical actions and environment constraints.
- [Sources](07-sources.md) and research notes: evidence behind technical choices, not proof of integration.
- [Agent prompts](08-agent-prompts.md): handoff templates; they do not supersede contracts or execute a run by themselves.
- [Autonomy and research](14-autonomy-and-research.md): investigation triggers, evidence-driven diagnosis and handling external blockers.
- [Quality gates](13-quality-gates.md): the user's required independent-review, repair and practical-test process for all deliverables.

When these disagree, the latest explicit user instruction governs intent; the owning document governs its technical detail. Correct stale summaries rather than treating repeated statements as independent authorities. For technical compatibility, actual versioned evidence takes precedence over untested proposals.

## Before yielding to another session

Update the owning file for each changed decision or finding, then reconcile status and work/readiness registers. Record the last successful command, observable result, remaining failure and smallest next action. Release file ownership or identify still-running work. Never leave a task marked passed because an agent said it was done without evidence.

Run the public context check/export after documentation changes. Do not export `.env`, account PDFs, Wi-Fi credentials, private media or raw transcripts. The archive's companion SHA-256 identifies that snapshot; it does not establish a Git commit or a remote push.
