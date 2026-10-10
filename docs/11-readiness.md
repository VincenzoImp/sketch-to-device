# Access and readiness register

This file distinguishes user input, work the assistant can perform, physical observation and environment restrictions. It is the canonical place for unblock conditions; [status](00-status.md) summarizes it. Observations below were made on 10 October 2026. Recheck relevant environment capabilities once in a new session or after a material change; do not repeat the same failed probe indefinitely.

## Current conditions

| ID | Condition and last evidence | Owner and next action | What actually unblocks it |
| --- | --- | --- | --- |
| R01 | **First voice-generated physical flow passed with speech/title limitation** | Gemini completed with two execution pairs and 24,026 effective tokens. Rocket Tap became Rocket Tata; production requirements false/null invoked generic checks. Independent post-install strict 15-second tests passed five checkpoints | Verify STAR TAP sketch/voice and broader fidelity; do not claim strict production checks or full transcript accuracy. Source remains frozen |
| R02 | **Fixture and generated app installed; physical behavior and ordinary reboot passed** | Sequence 6 rocket_tata has exact ACK. User confirms Start, 15-second scoring/final score, Play again reset, phone confirmation and playable app after reboot without flash. Actual served-byte C parsing passed ASan/UBSan | Second generated visual app, interrupted-install/power-loss and remaining negative/repeatability checks still need evidence. Ordinary reboot is no longer pending |
| R03 | **Working hotspot/current endpoint delivered the generated app** | All four delivery ACK stages match sequence 6 app/version/hash on the refreshed endpoint | Preserve network/service/endpoint. Observe a new deployment identity for the next request; no repeated provisioning or flash is needed |
| R04 | **Session environment blocker:** managed shell DNS fails and localhost bind returned PermissionError (errno 1). The user's normal terminal reached both provider hosts successfully | Assistant uses an authorized execution environment when available; the user ran one concrete diagnostic command | Working downloads, outbound requests and service execution for the implementation environment; normal-terminal success does not change this session's managed permissions |
| R05 | **Environment blocker:** creating workspace `.git` returned Operation not permitted | Assistant uses the supported repository workflow in an environment that permits the operation | Successful repository initialization or an existing writable checkout; user has already authorized it |
| R06 | **GitHub CLI/account ready:** gh2.102.0 installed; user completed browser login successfully | Publisher's seven tests and independent review, including exact-commit push, passed. Wait for a stable reviewed source snapshot before initial publication | Verified public repository URL and commit; no repo has been published yet |
| R07 | **Toolchain and actual physical voice path verified to stated scope** | Host suite: 131 passed at 14:37:53. Later served-app strict host checks and native C sanitizer parsing passed. Physical controls and ordinary reboot are user-confirmed | Visual repeat, second generated app and remaining fault/rehearsal cases remain open. No new setup permission is needed |
| R08 | **Second observer active; STAR TAP visual/voice input being prepared** | First observer ended with exact sequence 6 ACK and is archived. New 600-second watch began around 14:52 excluding four prior phone jobs; current store still has sequence 6 and no new job. User clarified prior App installed reply meant Rocket Tata | Receive the new sketch/voice 20-second STAR TAP input, then verify a distinct job/ACK/behavior. Old phone success is not a second result |
| R09 | **Organizer detail missing:** opt-in mechanism, submission URL and pitch duration not in supplied public material | Assistant inspects any new official instructions; user relays onsite-only information if needed | Actual organizer directions and opt-in completion; does not block context/schema work |

Private Wi-Fi/account material must stay in local configuration or a proper secret store. Do not publish SSIDs, passwords, account PDF contents or API keys just to make a handoff complete. A public clone intentionally lacks local credentials and private source files.

The currently flashed diagnostic firmware can seed its clock from a trusted local build timestamp when needed, then continues SNTP attempts. This is not proof of accurate synchronized time. Certificate-chain, hostname and validity-period checks are enabled; target configuration and wrapper linkage were independently checked before the successful flash. The earlier missing date setting did not explain the connection failure, and the earlier label did not establish NTP as its cause. No certificate-verification bypass is proposed.

## What the user still needs to provide

Nothing further is required to explain the product intent, hardware model, phone platform, partners, language, team size or setup authorization. Do not ask those again.

Hotspot availability and credentials are supplied, and actual device HTTPS/ACK now passes. Do not request network details again without a new concrete failure. Fixture controls and speech comparison already passed their stated checks. Service/endpoint setup, first generated-app controls and ordinary reboot are complete. The user is preparing the new sketch/voice request; pending physical actions concern that distinct app and remaining fault/rehearsal checks.

Human involvement is only conditional: an account login/connection that cannot be performed by an existing authenticated tool, inaccessible Wi-Fi provisioning information, physical interaction with the board/phone during tests, or organizer instructions available only on site. The assistant owns dependency installation, SDK research, version selection, code generation, tests and documentation.

## Remaining acceptance dependencies

Implemented components and successful setup do not establish the complete product:

- R02/R07 have fixture/generated behavior and ordinary reboot evidence. A second generated app and physical interrupted-install/previous-app safety tests remain open.
- R01/R04 have one working voice-generated physical game with a title mismatch; full transcript/visual fidelity and broader repeatability remain open.
- R03/R08 have the complete first voice-generated physical flow. Visual input and a second generated result remain unproved.
- R05/R06 govern public delivery and provenance; their failure does not prevent independent local implementation work.

Detailed smoke tests live in [hardware](research/hardware.md), [Gemini](research/gemini.md) and [partners](research/partners.md). Their gate results belong in [the work ledger](12-work-ledger.md), with exact evidence rather than repeated prerequisite lists.

## Updating a readiness entry

Record the observable result, date, environment, owner and next action. Remove a resolved user question; retain a terse historical failure only when it explains the next choice. Distinguish invalid credentials, missing credentials and a request that never reached the provider. Never turn a temporary restricted environment into a claim that the user's machine or account cannot perform the work.
