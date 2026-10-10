# Session handoff

## One-minute state

The user wants one Android request to create and install an app on the physical Waveshare device. The demo works for two separate generated games: voice sequence6Rocket Tata (including ordinary reboot) and photo-only sequence7Star Tap. The voice title was misrecognized; photo-only did not include the proposed20-second narration. Two later color-button jobs failed at the provider and left Star Tap active. Exact evidence and limits live in [the ledger](12-work-ledger.md).

**Current correction:** the user expected real app programming with useful documentation, web research, graphics/assets and broad device features, not a fixed5-widget/7-action language. They explicitly request pragmatic feasibility checks, preservation of this direction and frequent public commits. [Programmable platform](15-programmable-apps.md) supersedes the old permanent-DSL boundary. The selected first experiment is official QuickJS-NG0.14.0, preserving IDF5.5.5/BSP/LVGL and existing apps. The isolated engine works on the host and cross-compiles for P4; no programmable app runtime is integrated or deployed yet.

Local source includes tested0.2button colors, expanded normalized media, reviewed provider diagnostics/timing and an incremental publisher. Agent SDK/skills, web-tool declarations and an isolated engine probe are implemented in source. The source runtime0.2binary has compiled but is not flashed; the current service/device still represent the previous accepted baseline. QuickJS source verification is resolved; actual host resource tests and isolated target build passed. Do not ask for another download.

The latest public checkpoint is verified at [GitHub](https://github.com/VincenzoImp/sketch-to-device), commit aab9796974e0bbb9b2a65b0bc6df88f4a5cb0f36 with 135 audited files and the initial commit preserved. Later edits are not automatically committed. Managed Git metadata remains read-only and network/serial restricted despite user authorization; [readiness](11-readiness.md) owns those facts. The reviewed checkpoint helper needs a normal-Terminal execution only after a coherent public slice is ready.

## Next actions

1. Check time, tools and active ownership in [the ledger](12-work-ledger.md). Preserve the working service, endpoint, hotspot and saved app.
2. Continue from the passed engine/resource/P4-build gates and real host QuickJS/LVGL UI proof. Package delivery, timers, native allocation failure and target UI execution still need implementation/evidence. Keep difficult platform migrations separate from the working demo.
3. Compare the faster managed model against the existing default using identical SDK/tools and exact request checks, then coherently activate the accepted source. The latest live trace showed a documentation-read loop; source now prioritizes an early runnable draft. The lookup prohibition is already removed in source. Image-generation/custom-function research is complete; a broker and device asset path remain further implementation. Do not advertise APIs the device cannot execute.
4. Reconcile source contracts/tests/docs, audit public files and publish reviewed checkpoints with verified remoteSHA. Keep private media/configuration out of the public tree.
5. Activate a coherent tested slice before a fresh live request. Remaining product gates include combined photo+voice, intent/reference fidelity, physical fault recovery and rehearsal. Ordinary reboot and a second generated app already have evidence; do not repeat them as missing setup.

The event and prior17:00ready-by target are on10October2026, Europe/Zurich. The user says there is time for this correction but explicitly asks for pragmatism. Check actual time and scope instead of enforcing an old self-imposed feature freeze or promising an unmeasured migration deadline.

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
