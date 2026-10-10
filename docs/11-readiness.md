# Access and readiness register

Updated: 10 October 2026. Authorization and actual tool access are separate. The user wants autonomous work with questions only when an unavailable operation or physical observation requires them.

## Current conditions

| ID | Observed condition | Next action |
| --- | --- | --- |
| R01 providers | Private keys exist; actual voice generation used Gradium and Gemini. Photo-only generation also installed successfully | Keep keys private; verify new SDK/tool configuration in a separate observed live run after local review |
| R02 physical board | ESP32-P4rev3.2/16MiB; backup verified. Touch, generated apps and ordinary reboot of voice app passed | Preserve storage/current app; programmable engine/peripherals and fault recovery need their own physical evidence |
| R03 companion | Android site, recording, upload and exact installed confirmation passed | Keep existing site/service running; source changes require coordinated activation, not an assumed hot reload |
| R04 network | Android cellular hotspot resolved captive-portal connection issue; device HTTPS works | Preserve hotspot credentials. Do not ask for them again or disable certificate checks |
| R05 managed permissions | Earlier Git/network failures are historical. Current full-access profile enables filesystem/network; direct publication and remote verification passed | Execute authorized operations directly. Check actual serial/provider access when needed; do not infer their success from Git access |
| R06 public repository | Pre-redesign158-file commitd223469e89f2fca6057ff97c01598fa02ede3c53 verified at [GitHub](https://github.com/VincenzoImp/sketch-to-device) | Periodic public commits are required. Reviewed [checkpoint helper](../scripts/checkpoint_github.py) audits, commits/pushes without force and verifies remote identity; new local work remains unpublished until it succeeds |
| R07 tested source vs deployed source | Runtime0.2color extension passed host/native review and was flashed after the service restart/new endpoint update | Fresh Hello Colors sequence12 exact ACK and physical color cycling passed; exact flashed image is privately frozen. Flappy refusal preserved it. Physical probes are held during the renewed full-chain planning task |
| R08 programmable engine | QuickJS-NG0.14.0 selected for isolated probe after comparing alternatives. Official source hash verified; actual sanitized host tests and standalone P4crossbuild passed | Real host QuickJS/LVGL bindings and failure recovery passed an isolated probe; its public reproduction wrapper also passed independent execution. Installed package support and physical execution/recovery remain separate gates |
| R09 onsite delivery | Organizer opt-in mechanism/submission URL/pitch duration not established by supplied material | Check actual organizer directions when needed; no invented submission completion |

Private Wi-Fi/account material stays in ignored configuration. Current firmware may seed time from a trusted local build timestamp while attempting SNTP; successful TLS is not proof of synchronized clock accuracy.

## Human-only involvement

No new product explanation, account key, board model, phone platform or setup authorization is required. Human involvement is limited to physical interaction/observation, an actual account login, organizer details only available onsite, or an operation newly demonstrated to be unavailable through tools. The assistant owns research, implementation, local tests, dependency preparation and documentation.

The source download is resolved; no further fetch is needed. The reviewed service restart and runtime0.2 flash have completed. The reviewed model comparison completed: both exact behaviors passed; Flash-Lite took40.007seconds versus139.112seconds for Flash on this one task. Flash-Lite is selected in the restarted service source; fresh Hello Colors passed exact activation and physical behavior. The following Flappy request demonstrated the current format limitation. Current work is the [full-chain redesign plan](16-final-platform-plan.md); implementation/probes are held during it and the existing demo remains usable. The user supplies the later prompt/image, and Gemini must author the app.

## Remaining acceptance dependencies

Voice Rocket Tata, photo-only Star Tap and text Hello Colors have physical behavior evidence; a second app is no longer a missing gate. Fresh combined photo+voice, faithful arbitrary small requests, interrupted-install/previous-app recovery, multiple repeat runs and rehearsal remain open. Programmable execution, graphics assets and peripheral services are new gates, not capabilities implied by the existing touchscreen success.

Record observable results, environment, owner and the smallest next action. Distinguish credentials failure from a call blocked before the provider. [The ledger](12-work-ledger.md) owns command/result history and [the audited release plan](16-final-platform-plan.md) owns the next implementation order. The earlier [platform exploration](15-programmable-apps.md) retains alternative/probe evidence.
