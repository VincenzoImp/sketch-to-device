# Session handoff

## One-minute state

**Latest instruction (D33): commit everything and shut down.** The supervisor, backend and HTTPS tunnel are stopped; port8787 has no listener and no project test/monitor/build process remains. No generation was busy at shutdown. Keep the project idle until the user requests resumption. USB power and the phone hotspot have not been switched off remotely. The D32 state below is the preserved last running state, not a currently available service.

**Completed stabilization request (D32): save Penguin Tap first, commit/push the reviewed work, fix remaining bugs, then let the user repeat end to end.** The private backup is complete and independently accepted. It preserves the original v3 package/source, matching configured firmware and a consistent database snapshot in `private/saved-apps/penguin-tap-v3/`. Never publish those private files. An additional verified stabilized v8 snapshot is retained under `private/saved-apps/`; the ledger records its exact directory and manifest hash.

Runtime0.3.0 is flashed; its last running connection was verified before the intentional shutdown. The reviewed activation, recovered-app acknowledgment, startup-budget and PSRAM corrections are installed. Penguin Tap v8/sequence24 has an exact active acknowledgment; source/assets remain Gemini-authored sequence17 unchanged. Two consecutive replacements without an intervening reboot passed with exact ACKs; the second observed three engine instances with257015internal bytes free. These are delivery diagnostics, not a fresh generation or physical gameplay proof. The ledger owns detailed timing, failures and recovery evidence; a clean exclusive reset restored version8 with no HTTP/TLS failure, panic, stack overflow or assertion.

Gemini must author apps from user inputs; no coordinator-written games or hidden templates. The available programmable SDK exposes ordinary JavaScript, canvas, input, time and packaged images. Camera/microphone/speaker APIs are not implemented. Text, image and audio remain valid alone or combined. Preserve legacy schema 1 compatibility and all restore images.

The live service endpoint/identity and hotspot credentials are private. Full filesystem/network access and serial operations are available. Do not repeat obsolete requests for manual Terminal work. The completed stabilization implementation checkpoint is published at `1334cfd1eed5150537f39f1c809ebf9c2c2b9ece` (213 reviewed files), retaining earlier history; [the ledger](12-work-ledger.md) owns later publication evidence and current file ownership. The new supervisor supports `scripts/run_demo.py --restart-backend` without changing the endpoint; it refuses an active generation.

## Next actions

1. The requested backup and reviewed stabilization checkpoint are complete and activated. Preserve them.
2. Preserve the accepted physical replacement/reboot evidence and immutable private backups. Provider termination is still unconfirmed. Leave services stopped under D33.
3. Keep the reviewed public history current and verify remote main before another checkpoint; the additional v8 snapshot is already verified and the companion is intentionally offline.
4. Only after the user requests resumption, restart the service and reconcile its new tunnel endpoint with the private device configuration before a fresh prompt/media test. Then verify exact installation plus physical gameplay. Report remaining capability limits honestly; do not present a host simulator or emergency republish as that end-to-end result.

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
