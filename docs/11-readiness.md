# Access and readiness register

Updated: 10 October 2026. Authorization and actual tool access are separate. The user wants autonomous work with questions only when an unavailable operation or physical observation requires them.

## Current conditions

| ID | Observed condition | Next action |
| --- | --- | --- |
| R01 providers | Private keys exist; actual voice generation used Gradium and Gemini. Photo-only generation also installed successfully | Keep keys private; verify new SDK/tool configuration in a separate observed live run after local review |
| R02 physical board | ESP32-P4rev3.2/16MiB; backup verified. Touch, generated apps and ordinary reboot of voice app passed | Preserve storage/current app; programmable engine/peripherals and fault recovery need their own physical evidence |
| R03 companion | Android site, recording, upload and exact installed confirmation passed | Keep existing site/service running; source changes require coordinated activation, not an assumed hot reload |
| R04 network | Android cellular hotspot resolved captive-portal connection issue; device HTTPS works | Preserve hotspot credentials. Do not ask for them again or disable certificate checks |
| R05 managed permissions | Git index writes failedEPERM; GitHub/localhost access denied; official component download failed network resolution. User's normal Terminal can perform these | Complete/review local work first; ask for only the precise unavailable command. Do not bypass restrictions through a relay |
| R06 public repository | Initial100-file commit8826f2edb8ab662cc2e524e4867661832c8d04cd verified at [GitHub](https://github.com/VincenzoImp/sketch-to-device) | Periodic public commits are required. Reviewed [checkpoint helper](../scripts/checkpoint_github.py) audits, commits/pushes without force and verifies remote identity; new local work remains unpublished until it succeeds |
| R07 tested source vs deployed source | Runtime0.2color extension compiled forP4 and passed host/native review; current device still0.1. New media/provider source not fully loaded by running service | Coordinate firmware update and service restart only when reviewed slice is ready; a new tunnel URL also needs device configuration update |
| R08 programmable engine | QuickJS-NG0.14.0 selected for isolated probe after comparing alternatives. Official source hash verified; actual sanitized host tests and standalone P4crossbuild passed | Graphical bindings, installed package support, physical execution and recovery remain separate gates; no production migration yet |
| R09 onsite delivery | Organizer opt-in mechanism/submission URL/pitch duration not established by supplied material | Check actual organizer directions when needed; no invented submission completion |

Private Wi-Fi/account material stays in ignored configuration. Current firmware may seed time from a trusted local build timestamp while attempting SNTP; successful TLS is not proof of synchronized clock accuracy.

## Human-only involvement

No new product explanation, account key, board model, phone platform or setup authorization is required. Human involvement is limited to normal-Terminal operations unavailable in this managed session, physical interaction/observation, an actual account login, or organizer details only available onsite. The assistant owns research, implementation, local tests, dependency preparation and documentation.

The source download is resolved; no further fetch is needed. No new flash, service restart or generation is currently requested. The existing demo should remain usable.

## Remaining acceptance dependencies

Two distinct generated physical apps are established; a second app is no longer a missing gate. Fresh combined photo+voice, faithful arbitrary small requests, interrupted-install/previous-app recovery, multiple repeat runs and rehearsal remain open. Programmable execution, graphics assets and peripheral services are new gates, not capabilities implied by the existing touchscreen success.

Record observable results, environment, owner and the smallest next action. Distinguish credentials failure from a call blocked before the provider. [The ledger](12-work-ledger.md) owns command/result history and [the platform plan](15-programmable-apps.md) owns the correction in direction.
