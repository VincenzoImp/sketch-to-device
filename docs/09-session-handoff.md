# Session handoff

## One-minute state

**Latest instruction: plan a serious redesign of the entire input → agent → generated app → device path.** The user will supply the actual prompt and image; the product's Gemini agent must write app-specific layout, logic and behavior. Do not hand-build whack-a-mole, use complete hidden app templates or define a six-app whitelist. [The revised plan](16-final-platform-plan.md) owns scope and sequence. Feature changes/live probes are held for this planning deliverable; durable implementation authorization does not establish deployed support.

Production is still AppSpec0.2. Voice Rocket Tata worked and survived reboot; photo-only Star Tap worked; fresh Hello Colors sequence12 reached exact activation and user-confirmed color cycling. Flappy Bird was refused and preserved Hello Colors. No generated JavaScript has been delivered or run physically. The QuickJS/LVGL host proofs and P4 cross-build establish feasibility, not the production runtime or peripheral APIs.

The selected design replaces the AppSpec authoring target with ordinary JavaScript, an extensible device SDK, job-owned assets and actual trusted execution tools. Preserve working drivers/authentication/transport and schema1 compatibility. Google AI Studio is a development/hosting option; managed Antigravity through Interactions remains the selected programmable harness. Pi is a researched fallback, not an installed dependency. Ordinary app logic changes must require no firmware edits or app templates.

Full filesystem/network permission is now enabled. Direct publication and GitHub access succeeded; earlier read-only Git/network restrictions are historical. Serial and new provider-tool operation still need their own actual checks when implementation resumes. Verified checkpoint before this redesign revision: [d223469](https://github.com/VincenzoImp/sketch-to-device/commit/d223469e89f2fca6057ff97c01598fa02ede3c53),158files matched to the reviewed snapshot and remote main. Current planning edits need a separate reviewed commit.

## Next actions

1. Finish independent review/reconciliation/publication of the revised plan. Preserve the running endpoint, hotspot, current app and frozen0.2 restore image; no new generation or flash is needed for planning.
2. The first future implementation gate freezes shared package/SDK/tool/recovery contracts and proves a real managed custom-function round trip. The ignored draft has known cancellation defects and must be fixed/reviewed before live use. A fixed-program probe proves transport only.
3. Build the shared host/device JS core, pointer/time/graphics, assets and actual source-authoring tools as one end-to-end slice. The user later supplies the prompt/image; Gemini must author and test the resulting app. Verify exact installation plus rejection/recovery behavior physically.
4. Request unseen behavior changes without editing platform code. Qualify the six example requests and broader SDK modules, resource limits, fault handling and stable hosting separately. Do not wait for every peripheral to prove the first genuine programmable path, or call that first path the complete platform.

Flash-Lite remains the measured default: one same-input comparison passed in40.007seconds versus139.112seconds for Flash; both used200k tokens/600seconds. This is not a universal speed ranking. The earlier11–22engineer-hour hardware estimate is neither per-app latency nor an elapsed-time promise. Measure generation/tool/testing/delivery phases and re-estimate from actual integration.

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
- [Release plan](16-final-platform-plan.md): current audited programmable scope and implementation order; [pipeline](05-execution-plan.md): legacy gate definitions and repair strategy; [work ledger](12-work-ledger.md): actual gate state and owner.
- [Decisions](10-decisions.md): origin, rationale and decision status; [readiness](11-readiness.md): access, physical actions and environment constraints.
- [Sources](07-sources.md) and research notes: evidence behind technical choices, not proof of integration.
- [Agent prompts](08-agent-prompts.md): handoff templates; they do not supersede contracts or execute a run by themselves.
- [Autonomy and research](14-autonomy-and-research.md): investigation triggers, evidence-driven diagnosis and handling external blockers.
- [Quality gates](13-quality-gates.md): the user's required independent-review, repair and practical-test process for all deliverables.

When these disagree, the latest explicit user instruction governs intent; the owning document governs its technical detail. Correct stale summaries rather than treating repeated statements as independent authorities. For technical compatibility, actual versioned evidence takes precedence over untested proposals.

## Before yielding to another session

Update the owning file for each changed decision or finding, then reconcile status and work/readiness registers. Record the last successful command, observable result, remaining failure and smallest next action. Release file ownership or identify still-running work. Never leave a task marked passed because an agent said it was done without evidence.

Run the public context check/export after documentation changes. Do not export `.env`, account PDFs, Wi-Fi credentials, private media or raw transcripts. The archive's companion SHA-256 identifies that snapshot; it does not establish a Git commit or a remote push.
