# Session handoff

## One-minute state

**Latest instruction (D32): save Penguin Tap first, commit/push the reviewed work, fix remaining bugs, then let the user repeat end to end.** The private backup is complete and independently accepted. It includes the exact installed package/source, matching configured firmware and a consistent database snapshot in `private/saved-apps/penguin-tap-v3/`. Never publish those private files.

Runtime 0.3.0 is flashed and connected. A reproduced checkpoint-identity race was fixed, reviewed and tested in the real owner harness. Penguin Tap v3/sequence 19 has an exact active acknowledgment. Its logic/assets are unchanged Gemini-authored sequence 17 output, republished under a fresh intent/version after trusted execution; this was the user's emergency installation request, not a fresh one-action generation proof. Actual reset/boot restoration passed; touch/gameplay still awaits user observation. A later same-source replacement failed initialization and correctly recovered v3; the ledger owns its diagnosis.

Gemini must author apps from user inputs; no coordinator-written games or hidden templates. The available programmable SDK exposes ordinary JavaScript, canvas, input, time and packaged images. Camera/microphone/speaker APIs are not implemented. Text, image and audio remain valid alone or combined. Preserve legacy schema 1 compatibility and all restore images.

The live service endpoint/identity and hotspot credentials are private. Full filesystem/network access and serial operations are available. Do not repeat obsolete requests for manual Terminal work. The stabilization checkpoint is published at `99b2be55c97addeb731e6f6b848b5c4df65dfb2f` (209 reviewed files), after `4d11954`; [the ledger](12-work-ledger.md) owns later publication evidence and current file ownership. The new supervisor supports `scripts/run_demo.py --restart-backend` without changing the endpoint; it refuses an active generation.

## Next actions

1. The requested backup and reviewed stabilization checkpoint are complete and activated. Preserve them.
2. Activate the independently accepted initialization-budget correction and repeat the bounded same-source physical replacement test. Provider termination is still unconfirmed. Preserve the active app/service while testing.
3. Test and independently review coherent fixes, publish checkpoints, and activate them with verified connection and recovery state.
4. Let the user submit their own fresh prompt/media and verify exact installation plus physical gameplay. Report remaining capability limits honestly; do not present a host simulator or emergency republish as that end-to-end result.

There is no per-app firmware compilation. Flash-Lite remains the measured default; an earlier controlled comparison took 40.007 seconds versus 139.112 seconds for Flash, not a universal ranking. Measure generation/tool/delivery phases rather than guessing the source of delay. [The release plan](16-final-platform-plan.md) retains the broader acceptance cases and physically unproved extensions.

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
