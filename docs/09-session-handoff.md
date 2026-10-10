# Session handoff

## One-minute state

**Latest instruction: stop implementation/probing, audit the whole platform, and plan one coherent final release.** The user explicitly expects Snake, Flappy Bird, calculator, clock, stopwatch and uploaded-image whack-a-mole. [The audit and release plan](16-final-platform-plan.md) owns the next implementation sequence; [platform exploration](15-programmable-apps.md) remains research/probe history.

The production runtime is still AppSpec0.2. Voice Rocket Tata worked and survived reboot; separate photo-only Star Tap worked. After a coordinated service restart/firmware flash, fresh Hello Colors sequence12 reached exact activation and user-confirmed color cycling. The following Flappy request returned unsupported and preserved Hello Colors. This is an architectural limitation, not a reason to repeat the prompt. No generated JavaScript has been delivered or run on the physical device.

The accepted QuickJS engine/UI host proofs and isolated P4 builds establish feasibility. They do not include production packages, general timing/drawing/images, durable callback-failure recovery or physical resource measurements. The public target build reproduction is independently accepted; the partial ignored physical-flash helper is parked, unreviewed and must not run.

Flash-Lite is the restarted service's selected source default, with200k tokens/600seconds. The same-input comparison passed exact behavior in40.007seconds versus139.112seconds for Flash. The new audit also identified missing installed-device SDK selection, insufficient remote checker attestation, overwritten per-job traces and late-failure/current-health reporting. Existing backend AppSpec validation and role-separated transport remain useful and should be preserved.

Latest verified public checkpoint: [35e8d69](https://github.com/VincenzoImp/sketch-to-device/commit/35e8d69267ff5fea5b7c85cfbf0ced2813c72fb9),144files with earlier history intact. Later local work is unpublished. Git metadata remains read-only and network/serial restricted despite authorization; [readiness](11-readiness.md) records the actual boundary.

## Next actions

1. Preserve the running service, endpoint, hotspot, current app and exact verified0.2 restore image. No new generation, restart or flash is needed for this audit.
2. The [unified plan](16-final-platform-plan.md) passed hardware, agent and final cold-start review; public context checks passed158 files. Publish the reviewed checkpoint through the existing authorized helper; normal-Terminal execution is needed for the unavailable Git/network operation.
3. When implementation resumes, start at milestone0: freeze SDK/package/lifecycle contracts and prove a real same-engine checker tool route, either managed execution or a registered trusted backend function. Do not assume macOS/P4 binaries run in the managed Linux environment.
4. Build one generated calculator through the production lifecycle and exact recovery reporting. Then implement common time/input/canvas/assets and run all six fresh request cases plus an unseen composition. No app-specific firmware handlers or another series of AppSpec-only patches.
5. Complete physical fault/reconnect/compatibility and resource tests, fresh combined photo+voice, correlated timings, stable endpoint setup and rehearsal before declaring the release ready. Camera/audio services are separate follow-on gates, not implied capabilities.

The old17:00 target and event19:00 opt-in/20:00 demos are scheduling inputs, not evidence that this migration can fit them. The hardware-lane estimate alone is11–22 focused engineer-hours; backend broker/hosting work remains unsized. Keep the existing demonstrated flow available and state the actual scope honestly.

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
