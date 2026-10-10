# Project operating instructions

## Objective and current phase

**Latest user steering (10 October, after clarifying who authors the apps): plan the complete input-to-agent-to-package-to-device redesign for general app programming.** The user will supply the actual prompt and image; Gemini inside the product must create the app. The coordinator must not hand-build whack-a-mole or introduce game templates as a substitute. [The release plan](docs/16-final-platform-plan.md) owns this reassessment, including what to preserve, replace and add. The current deliverable is the independently reviewed plan and public checkpoint; hold feature changes, provider jobs and physical probes during it. Earlier implementation authorization persists, but finishing the plan does not imply a capability is deployed. Actual full filesystem/network access is now enabled and direct publication succeeded; do not ask for routine Terminal execution based on superseded restrictions. Preserve the working device/service and exact restore image.

Read [README.md](README.md), [session handoff](docs/09-session-handoff.md), [current status](docs/00-status.md), and relevant linked documents before working. Build toward this outcome: one prompt from an Android phone → a Gemini agent using real tools → a validated app package → an interactive app installed on the Waveshare ESP32-P4-WIFI6-Touch-LCD-3.5. Use Google DeepMind and Gradium substantively. The user has explicitly requested subagents and iterative verification.

The user has now authorized implementation and practical integration probes as well as context enrichment and public GitHub publication. Follow [the execution plan](docs/05-execution-plan.md) toward the real end-to-end outcome, updating it from observed progress. Necessary installations, configuration, reversible fixes and milestones need no renewed permission. Environment restrictions still apply; progress on independent work while recording concrete blockers. Do not build substantial integration-dependent code on untested assumptions.

All project artifacts must be in English: documentation, UI copy, source code comments, tests, agent prompts, demo scripts, and generated sample content. Communicate with the user in Italian. Keep original private PDFs unchanged.

## Resume without the original conversation

- Follow the role-specific reading map in [session handoff](docs/09-session-handoff.md); do not load all research or any private files simply to recover context.
- Read [decision origins](docs/10-decisions.md), [readiness and unblock conditions](docs/11-readiness.md), and [actual work and ownership](docs/12-work-ledger.md). These distinguish user requirements, selected designs, proposals and untested claims.
- Select the next incomplete task within the latest user request. The ledger records current work; the [execution plan](docs/05-execution-plan.md) defines future gates. Do not confuse the two.
- On a new session, inspect current tools, time and local state before treating previous environment restrictions as still active. Recheck after a material change, not repeatedly without new evidence.
- Both provider keys are configured privately and the board has been connected. Do not request those again unless a concrete new test establishes a problem. The selected device network is the user's Android cellular hotspot: the event Wi-Fi has a confirmed captive portal, and the hotspot now has actual device HTTPS and exact fixture-ACK evidence. Keep its credentials private.
- Before yielding, update the owning document and reconcile status, readiness and task ownership. Record commands/results and next actions without secrets. Run the [public context auditor](scripts/check_context.py) after documentation changes.

## Product decisions that must survive handoffs

- The main demo is one prompt followed by a working app appearing on the device. The candidate is a simple 10-second tap game; the demo language is English.
- Pairing and network setup happen before the demo. The phone is Android. Camera and battery availability are user-confirmed; physical functionality is untested until evidence exists.
- The single **Generate and install** action for the selected paired device authorizes a reversible, validated app-package installation. Do not add mandatory transcript confirmation, preview approval, or a second install button to this path.
- An optional preview may accompany progress. Chat iteration and a second generated version are P1, not prerequisites for the initial success state.
- Package installation must preserve the last known working app and reject invalid artifacts. Firmware flashing is a separate setup operation, not an operation generated apps can request.
- Google DeepMind and Gradium are the selected partners. Entire is optional and parked; do not install or enable it without a concrete project need. Do not introduce a partner-eligibility question without evidence of a relevant event rule.
- Public GitHub publication of the sanitized project is authorized. Exclude original PDFs, `.env`, private input media and credentials. Do not claim publication until the repository and push are verified.
- The user is the sole human participant; worker lanes represent AI agents, not human teammates.

## Evidence and decisions

- Distinguish sourced facts, user preferences, proposals, and actual test results.
- Later user instructions override proposals in these documents. Update status and decisions before propagating a change to other agents.
- The file ownership map in [session handoff](docs/09-session-handoff.md) determines where a fact belongs. Prefer links over maintaining duplicate technical contracts. Capture scope changes and superseded assumptions in the [decision register](docs/10-decisions.md).
- Use current official API/SDK sources and record versions actually tested. Research notes are not authenticated smoke tests.
- Do not infer silicon revision, pins, ESP-IDF compatibility, credentials, or quota from the board name. Capture verification evidence.
- The user has explicitly reopened the runtime scope: real programmable apps, a consultable SDK and broad device capabilities are the current priority. Preserve the working demo while testing the replacement. A new capability needs a concrete implementation, compatibility strategy and practical evidence; the earlier MVP freeze is not a user prohibition.

## Active research and implementation truth

Follow [autonomy and research](docs/14-autonomy-and-research.md). Seek current official sources when an uncertainty can change the next action; turn hypotheses into small executable probes. Change diagnosis after repeated failure. Keep the plan adaptive and time-conscious. Code plus relevant practical tests establish implemented behavior; documentation records that evidence and never substitutes for it. Reconcile contradictory claims with actual artifacts before continuing.

## Collaboration

Follow [independent review and practical verification](docs/13-quality-gates.md) for every deliverable. This is an explicit user requirement: a different agent reviews the actual output, the author fixes material findings, and affected real checks plus substantive re-review continue until acceptance passes. Review covers supporting tools and documentation as well as the product. Do not claim unqualified perfection or use trivial green tests as proof of working behavior.

- The coordinator owns contracts, integration, status, and decisions.
- Use at most three workers alongside the coordinator. Assign independent tasks with explicit file ownership; avoid concurrent writes to one file.
- Every delegation states inputs, outputs, owned files, acceptance criteria, and known uncertainties. Delegation prompts and written reports are in English.
- Register active tasks and release ownership in [the work ledger](docs/12-work-ledger.md). Completed research agents are not automatically active implementation workers in a new session.
- A reviewer checks the material risks in another agent's work. Tests and actual device observations take precedence over agreement between agents.
- The final integration gate uses real Android input, authenticated providers and the physical Waveshare. Simulators/mocks cannot replace those proofs. Optimize only against measured needs, keeping the solution simple.
- After failure, isolate the cause, fix it, and rerun the relevant check. Do not repeat an unchanged attempt without new evidence. Use the loop budgets and fallback decisions in docs/05-execution-plan.md.

## Future implementation

- Keep the existing versioned AppSpec compatible while developing a separately versioned programmable app ABI. The selected first feasibility probe is QuickJS-NG; see [programmable apps](docs/15-programmable-apps.md). Agree contracts before parallel implementation.
- Generated programs require a controlled interpreter, resource budgets, bounded native APIs, lifecycle cleanup and recovery. The previous blanket ban on generated code was an implementation choice superseded by the user's request. This does not authorize apps to flash firmware, access credentials or execute host commands. Keep secrets out of app bundles, frontend code, logs, and remote agent contexts.
- Revalidate generated artifacts on the backend. A model's completed status or statement that tests passed is insufficient evidence.
- Report installed only after the device acknowledges the exact app ID, version, and hash. Do not present a simulator as physical hardware.
- Follow the selected BSP's concurrency model for LVGL rendering and updates. Keep the previous application active if validation fails.
- Record fallbacks and display them honestly. Do not silently weaken physical-device or real-partner requirements.

## Private material and delivery

Original PDFs contain correspondence and temporary credentials. Do not copy them into public sources, remote prompts, Entire sessions, or commits. Use sanitized summaries in docs/. Do not print `.env` or dump the process environment. `.gitignore` does not remove already tracked files; inspect actual tracked content before any later authorized publication.

Record evidence without personal data. Export required code, packages, evidence, and demo recordings before temporary accounts expire. Do not claim completion until docs/06-validation-demo.md acceptance criteria pass or remaining limitations are stated explicitly.
