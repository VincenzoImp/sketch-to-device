# Hardware probe and bring-up evidence

**Latest checkpoint, 10 October:** an Android voice request produced a real app acknowledged by the board at 14:48 Europe/Zurich. The user confirmed its 15-second game behavior and restoration after a reboot without flashing. The requested title was mistranscribed; interruption tests remain open. See the final section. Earlier sections retain their original probe scope and are historical.

Observed on **2026-10-10 at 10:18:43 UTC** in the managed macOS shell for this workspace. This is a narrow feasibility result, not a firmware or peripheral acceptance test. The user-confirmed board model and proposed software baseline remain in [hardware research](hardware.md); operational dependencies belong in [readiness](../11-readiness.md).

## Actual result

Command executed:

```sh
python3 -B scripts/probe_hardware.py --check-serial-access
```

| Check | Observed result | Meaning |
| --- | --- | --- |
| Platform | Darwin, arm64; Python 3.9.6 | A stdlib Python probe can execute locally |
| USB serial candidates | Exactly one matching character device | One plausible connected serial interface; the device path is deliberately omitted |
| Serial access | `opened_read_only` | One open with `O_RDONLY`, `O_NONBLOCK`, and `O_NOCTTY` succeeded, followed by close |
| IDF/flash tools on PATH | `idf.py`, `esptool`, `esptool.py` absent | Firmware identification/build tooling is not ready through PATH |
| Build tools on PATH | `clang` present; `cmake`, `ninja` absent | Host compiler presence does not provide the ESP RISC-V toolchain |
| Python modules | `esptool` and `serial` not found by the active interpreter | These modules are not available in this Python environment |
| Narrow IDF location check | No `export.sh` found | Checked the conventional user `esp/esp-idf`, `/opt/esp-idf`, and `IDF_PATH` if set; this was not an exhaustive disk search |
| USB metadata | `ioreg` query exited with code 1 | Vendor/interface identity was not established; the cause was not inferred from the exit code |
| Silicon/flash/firmware | Not probed | No revision, flash size, or installed firmware version was obtained |
| Display/touch/radio | Not tested | No BSP or end-to-end gate passed |

**Serial access is available in this execution context.** The remaining immediate bottleneck is acquiring a compatible toolchain through an authorized environment with working downloads, not reconnecting the already connected board. The probe did not retest the separately recorded DNS/localhost restrictions, inspect Wi-Fi configuration, or read credentials.

## Scope and reuse

[The probe script](../../scripts/probe_hardware.py) uses only Python's standard library. Its default mode enumerates and reports capabilities without opening a serial port:

```sh
python3 -B scripts/probe_hardware.py
python3 -B scripts/probe_hardware.py --help
```

Only `--check-serial-access` attempts a serial open, and only when exactly one candidate is present. The child process is bounded to one second; the separate USB inventory command is bounded to five seconds. The script does not read or write serial bytes, configure baud/termios, issue ioctls, request reset/bootloader entry, flash, install packages, or make network calls. It never prints serial paths, USB serial numbers, product names, SSIDs, or raw subprocess errors. Opening a port establishes access only; it does not identify the chip or prove any board behavior.

No passive boot-log read was performed. Without changing configuration or triggering a boot, a silent interface would not establish firmware/revision failure. Protocol identification should be a separate, explicit step using the installed toolchain, not speculative serial commands inside this inventory helper.

## Verification performed

The real access command above exited successfully and produced the sanitized results in the table. `--help` was also checked. Seven behavioral checks passed using synthetic data and mocked system boundaries, with no additional physical serial opens:

1. The worker opens only read-only/nonblocking/no-controlling-terminal and closes the descriptor; any byte read/write would fail the check.
2. A permission exception containing a synthetic private path/message emits only its error code.
3. Default, zero-candidate, and ambiguous-candidate modes never spawn a serial access attempt.
4. A child timeout returns a bounded failure result.
5. Unexpected fields in child output are withheld.
6. The complete default inventory does not open the serial device.
7. USB fixtures containing synthetic private identifiers yield counts only.

These checks establish the intended probe boundaries. They do not replace a silicon query, BSP build, flash, physical observation, or independent code review. Review status is recorded by the coordinator in [the work ledger](../12-work-ledger.md).

## Smallest practical next step

1. Make an authorized execution/download route available for the assistant; the known shell DNS restriction is recorded in readiness. Do not bypass restrictions or ask the user to repeat permissions already given.
2. Install and pin the identification/build tooling in a permitted location. Start with a current compatible esptool environment for chip identification, then the proposed ESP-IDF/BSP baseline once the silicon profile is known. Record versions actually used; availability of Python 3.9.6 alone is not a compatibility result.
3. Run a separate chip-identification/recovery-baseline step. Esptool communication can involve serial protocol traffic and bootloader/reset behavior; that was outside this probe and has not occurred.
4. Build and exercise the official display/touch example on the confirmed revision, then test the existing C6 hosted network stack. Only then extend the firmware with the canonical [AppSpec runtime](../04-contracts.md).

No firmware source was created from unverified pins, no firmware was flashed, and no existing device data was intentionally changed. The board's silicon revision, working peripherals, C6 firmware and device-to-backend networking remain open implementation evidence.

## Identification setup update — 10 October, around 12:46 Europe/Zurich

The coordinator verified an isolated `.tools/board-probe` environment with Python 3.9.6 and **esptool 4.11.0**, installed through the user's normal terminal; resolved dependencies are recorded in the ignored `.tools/board-probe.lock.txt`. The interpreter path must retain its venv location: resolving its executable symlink selects the base interpreter and loses the installed modules.

The subsequent managed-shell chip query failed with sanitized error **`serial_operation_denied`**. This supersedes the broad earlier statement that serial access is available: the read-only open succeeded, but esptool's read/write/configuration access did not. It does not establish a disconnected board, wrong silicon revision, or faulty hardware. Managed-shell DNS/download restrictions and serial permissions are separate blockers; successful normal-terminal downloads resolve neither permission inside this managed session.

[The identification wrapper](../../scripts/identify_board.py) is ready for a normal-terminal probe after independent review:

```sh
python3 -B /Users/vincenzo/hackathon/scripts/identify_board.py --probe
```

The wrapper requires exactly one enumerated USB serial candidate, invokes the fixed isolated interpreter with `-I -m esptool --port <private candidate> --no-stub flash_id`, captures all subprocess output, and kills/waits for the subprocess after a 30-second timeout. **This ROM identification query may reset the board or enter its bootloader; it does not write flash.** It emits only an allowlisted chip model, numeric silicon revision, flash size and controlled result/error codes. MAC addresses, serial paths/numbers and raw tool errors are withheld. Unknown chip/output formats produce an explicit incomplete-identification error instead of a guessed revision. The default command and `--help` do not access hardware.

Author checks passed: `--help`; default `not_requested`; seven synthetic tests covering sanitized successful output, permission/unknown output, default no-access, ambiguous-port refusal, exact command/venv path/timeout, timeout/launch-error redaction, and failure despite partial identity output. No additional physical query was attempted during wrapper development. The wrapper has not yet identified the real board; independent review and the user's normal-terminal result are the next evidence required.

### User-terminal result and partial-result correction

The user's normal-terminal run subsequently returned **ESP32-P4, silicon revision 3.2** with an esptool exit code of zero. ROM communication and the chip revision are established; flash capacity is not. The first wrapper incorrectly labeled the whole result `query_failed` when the flash-size line was absent or unrecognized. It now reports `partially_identified` for a valid chip/revision with successful esptool execution and unavailable flash size, distinguishing an explicit `Unknown` size from an unrecognized size line. It does not infer which occurred in that earlier run. Confirmed revision 3.2 selects the vendor's `rev3_x` build profile; flash-size verification remains outstanding before any flashing operation.

## Toolchain and display-example bootstrap

[The bootstrap script](../../scripts/setup_firmware_tools.sh) prepares tools and builds the official example without flashing:

```sh
bash /Users/vincenzo/hackathon/scripts/setup_firmware_tools.sh
```

It selects ESP-IDF **v5.5.5**, installs the P4 toolchain under `.tools/espressif`, and uses a workspace pip cache. The official [installation guide](https://docs.espressif.com/projects/esp-idf/en/v5.5.5/esp32p4/get-started/linux-macos-setup.html) supports Python 3.9 and custom `IDF_TOOLS_PATH`. The pinned [IDF tool manifest](https://raw.githubusercontent.com/espressif/esp-idf/v5.5.5/tools/tools.json) supplies checksummed macOS packages for CMake 3.30.2 and Ninja 1.12.1; `idf_tools.py install cmake ninja` avoids a separate Homebrew requirement.

The vendor checkout includes both display/touch and Wi-Fi examples, their local components, root configuration, documentation and schematic. Keeping that layout is necessary because the [display example CMake file](https://raw.githubusercontent.com/waveshareteam/ESP32-P4-WIFI6-Touch-LCD-3.5/main/examples/esp-idf/08_lvgl_demo_v9/CMakeLists.txt) imports a relative root configuration file. The build explicitly selects `rev3_x` with separate sdkconfig/build paths according to the [vendor revision guide](https://raw.githubusercontent.com/waveshareteam/ESP32-P4-WIFI6-Touch-LCD-3.5/main/docs/ci.md). No firmware write or erase command exists in the script.

Existing checkouts must match the official origins and recorded commit hashes. The first successful download records actual IDF/vendor SHA values in `.tools/esp-idf.commit` and `.tools/waveshare.commit`, and detaches the vendor checkout. The vendor SHA is not known before that download: web lookup did not expose a usable immutable commit, so none was invented. Resolved component dependencies still need their resulting lockfile recorded after configuration.

Author checks passed: `bash -n`; four synthetic command-flow executions proving first-run setup/build, repeat without recloning/reconfiguring, wrong-origin refusal and changed-commit refusal. Downloads, installers and build commands were mocked in those checks. The normal-terminal bootstrap/build remains a separate live test; this script and source research do not establish a successful toolchain installation or physical display behavior. C6 SDIO pin configuration must be inspected from the downloaded Wi-Fi component/configuration and the schematic before network bring-up; it was not inferred from a different board.


## Physical HTTPS delivery — 10 October, approximately 14:35 Europe/Zurich

The identified board is ESP32-P4 revision 3.2 with 16 MB flash. The reviewed custom runtime was built with ESP-IDF 5.5.5, the verified board pin configuration, and private Wi-Fi/service settings. The hotspot image at that checkpoint was 1,449,072 bytes with SHA-256 `d3bbb3bbff854277f6682731c7aaa0794d9b33496f317cb1cad13c888e77146f`. The original flash backup remains verified; the guarded setup helper preserves the dedicated app partition after its initial setup. Detailed build, parser and delivery evidence lives in the [firmware README](../../firmware/README.md).

The event Wi-Fi required a captive portal, according to the user. The device initially reached an IP event but received a 395-byte certificate that the unchanged Mbed TLS parser rejected. A verified Mac chain contained different bytes and parsed successfully on the host; the exact cause of that peer difference was not established. Certificate-chain, hostname and validity-period verification remained enabled in the final diagnostic firmware. No certificate trust bypass or SDK parser patch was introduced.

The user approved an Android hotspot with cellular uplink while the Mac kept its running service/tunnel. The first captured attempt after the actual Wi-Fi configuration change failed association, before any TLS request. After the user corrected hotspot settings, the existing firmware reconnect loop connected and the app changed on screen. This did not require a new source change or another flash.

The real backend then recorded `downloading`, `validating`, `activating`, and `active` acknowledgments for the exact Focus Timer fixture:

| Field | Verified value |
| --- | --- |
| App | `focus_timer` |
| Intent sequence | 5 |
| Version | 1 |
| Exact served package size | 1,152 bytes |
| SHA-256 | `afeb5dcae1bc7f93e1c570bab89cb3b2db6052b06e7a7296d8e526ac7349f2dc` |
| Desired identity equals active identity | True |

The coordinator and hardware worker independently inspected actual store state. The private acknowledgment snapshot was saved with mode 0600; no credentials, SSID, serial path, or raw UART output enter this note. This establishes actual authenticated HTTPS package delivery and exact device installation acknowledgment. The user subsequently confirmed Start, Pause/Resume, Reset and Menu → Apps on the downloaded app. Completion, Completed and Try again were not confirmed, and no instrumented timing measurement was collected. At that checkpoint a second installation and reboot recovery remained pending; the subsequent results are recorded below. No Gemini or Gradium call produced this fixture, so that fixture result alone did not establish the AI generation or complete Android happy path.


## Generated Android installation and ordinary reboot — 10 October

A fresh Android voice request reached Gradium and Gemini through the restarted service. Gemini completed with two paired code-execution calls/results and a checked source artifact. The backend assigned the published identity and revalidated the served bytes. At **12:48:46 UTC / 14:48 Europe/Zurich**, actual store evidence showed all four device acknowledgments and exact desired/active identity equality:

| Field | Verified value |
| --- | --- |
| App | `rocket_tata` |
| Intent sequence / package version | 6 / 1 |
| Exact served package size | 1,307 bytes |
| Served SHA-256 | `8f86a3239381b9592960b8716b81e1c5835551508d4c2f236a7bb4cd843ea9dd` |
| Source artifact SHA-256 before backend publication | `0dc7e8ab9afca3e14b0aed5dc53251237375cdbe0dc93161c293b5c59734cff4` |
| Active firmware SHA-256 | `94956bfbc4257046f9f22d054aac50632befdcad87a039becb79c3e10b6e8a8a` |

The source and served hashes represent separate byte sequences; remote execution evidence belongs to the source hash, while device acknowledgment and installation belong to the served hash. The archived served file passed the actual C parser in `--validate` mode under AddressSanitizer and UndefinedBehaviorSanitizer, with no diagnostics. No hardcoded ten-second fixture scenario was applied to that C check.

Independent host checks covered the intended 15-second tap-game scenario and additional scoring, deadline, restart, stale-event and shell-pause behavior. The user then confirmed Start, scoring taps, the final score after 15 seconds, Play again resetting score and countdown, and the phone's installation confirmation. After a reboot without flashing, the user explicitly confirmed that the same app returned and another game started. This demonstrates a real generated replacement after the earlier fixture and ordinary persisted-app restoration.

The requested title was **Rocket Tap**, but Gradium's transcript and generated app used **Rocket Tata**. The transcript also did not activate the original narrow production tap-game/duration detector; the strict 15-second host checks above were independent checks after installation. Do not claim perfect transcription or that production inferred those requirements correctly. Interrupted downloads, power loss during activation/NVS updates, and broader fault recovery remain physically untested. The ordinary reboot result does not substitute for those fault tests.

The exact package, host checks and observation are archived locally as `phone-generated-20261010T1247Z-app.json`, `phone-generated-20261010T1247Z-host.json` and `phone-generated-20261010T1247Z-observation.json` under ignored `artifacts/verification/`. The original host snapshot predates the user's touch/reboot confirmation; these subsequent observations are recorded here and in the coordinator's current validation evidence.
