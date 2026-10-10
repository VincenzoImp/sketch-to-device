# Hardware and app runtime

Historical research checked on 2026-10-10 using official documentation and repositories, before compilation, flashing, chip identification and physical tests. The proposals and unverified prerequisites below describe that initial research stage, not the present implementation state. Subsequent actual results, selected versions and remaining gates belong to [the work ledger](../12-work-ledger.md) and [readiness](../11-readiness.md); the [implemented architecture](../03-architecture.md) supersedes earlier design proposals. Do not repeat completed setup merely because this research originally listed it as pending.

## Recommendation

Install one ESP-IDF firmware with a small LVGL runtime. The model generates a JSON package describing screens, state, and allowed actions. The device downloads, validates, saves, and runs that package. The phone companion handles media capture and conversation; the backend interprets the material and generates the app. This produces installable apps whose interface and behavior change without rebuilding or reflashing the firmware.

The first path uses one board, preconfigured Wi-Fi, and a web companion on Android. The user enters a prompt, selects the paired device, and presses **Generate and install** once. Automatic checks then lead directly to an interactive app on the touch display. An optional P1 preview can accompany progress without becoming another approval step. The candidate demo is a 10-second tap-score game; English is accepted by the user. Conversational revisions are P1; package versioning and recovery remain part of the runtime.

## Confirmed board and verified specifications

The user confirmed **Waveshare ESP32-P4-WIFI6-Touch-LCD-3.5**, with camera and battery available. Do not confuse it with the 3.4C, 4.3, 4B, or the P4-WIFI6 without its integrated display. Reported availability is not a hardware test result.

| Component | Verified specification | Design consequence |
| --- | --- | --- |
| Display | 320 × 480, ST7796 controller, SPI | Small portrait UI; no HTML/browser runtime assumed on the board |
| Touch | FT6336, I2C | Interaction through LVGL |
| Memory | 32 MB PSRAM, 16 MB flash | Suitable for small interfaces; keep authoring videos off the device |
| Wireless | ESP32-C6 connected to the P4 over SDIO | The P4 itself has no Wi-Fi/Bluetooth radio |
| Camera/audio | OV5647 MIPI-CSI, ES8311 codec, microphone and speaker | Available peripherals, unnecessary for initial phone-based authoring |
| Power/programming | Separate USB-UART and USB OTG Type-C ports; AXP2101 | Start with wired power and debugging |

Sources: [product page](https://www.waveshare.com/product/iot-communication/esp32-p4-wifi6-touch-lcd-3.5.htm), [official overview](https://docs.waveshare.com/ESP32-P4-WIFI6-Touch-LCD-3.5).

## Software baseline to freeze after the first test

Use the [official board repository](https://github.com/waveshareteam/ESP32-P4-WIFI6-Touch-LCD-3.5). Start with `08_lvgl_demo_v9` for display/touch and `04_wifistation` for networking. `06_I2SCodec` and `09_video_lcd_display` are optional audio/camera references. `11_esp_brookesia_phone` and `12_esp32-p4-eye` add substantial code unnecessary for the first runtime.

| Layer | Documentation evidence at research time | Initial proposal |
| --- | --- | --- |
| ESP-IDF | Official CI declares builds on v5.5.5 and v6.0.2 | Start with v5.5.5, test the actual chip, then pin it |
| BSP | LVGL example requires `waveshare/esp32_p4_wifi6_touch_lcd_3_5 ==2.0.2` | Retain this version |
| LVGL | The same example requires `lvgl/lvgl 9.4.*` | Resolve a patch version and record it in the lockfile |
| Networking on IDF <6 | `esp_wifi_remote 0.14.*`, `esp_hosted 1.4.*` | Use this pair only after testing the installed C6 firmware |
| Networking on IDF ≥6 | `esp_wifi_remote >=1.6,<2.0`, `esp_hosted >=2.12,<3.0` | Alternative; do not implicitly update the C6 |

Sources: [CI and revisions](https://raw.githubusercontent.com/waveshareteam/ESP32-P4-WIFI6-Touch-LCD-3.5/main/docs/ci.md), [LVGL manifest](https://raw.githubusercontent.com/waveshareteam/ESP32-P4-WIFI6-Touch-LCD-3.5/main/examples/esp-idf/08_lvgl_demo_v9/main/idf_component.yml), [Wi-Fi manifest](https://raw.githubusercontent.com/waveshareteam/ESP32-P4-WIFI6-Touch-LCD-3.5/main/examples/esp-idf/04_wifistation/main/idf_component.yml).

The [Waveshare component policy](https://raw.githubusercontent.com/waveshareteam/ESP32-P4-WIFI6-Touch-LCD-3.5/main/docs/components.md) specifies that the BSP uses `esp_lvgl_adapter`. Example 12 stays on LVGL 8.3 for existing assets; do not mix its UI code into the LVGL 9 baseline. The BSP fixes RGB565 at 16 bits with big-endian order; images/colors must respect that contract. Its [display header](https://raw.githubusercontent.com/waveshareteam/Waveshare-ESP32-components/master/bsp/esp32_p4_wifi6_touch_lcd_3_5/include/bsp/display.h) exposes the 320 × 480 geometry.

Before implementation, record the selected Waveshare commit, ESP-IDF tag, exact resolved component versions, silicon profile, configuration, and observed C6 firmware version. The `main/master` URLs are mutable research references, not a technical lockfile.

## Bring-up traps to resolve before the application pipeline

1. **Silicon revision.** Waveshare distinguishes `rev1_3` for rev1.x silicon and `rev3_x` for rev3.x; the binaries are incompatible. This is a processor revision, not a PCB revision. Read the boot log/probe before flashing, and select separate profile/build directories. Do not bypass the flasher's revision check. The repository currently defaults to rev3.x. [Revision guide](https://raw.githubusercontent.com/waveshareteam/ESP32-P4-WIFI6-Touch-LCD-3.5/main/docs/revisions.md)
2. **SPI display.** Some paragraphs in the [Waveshare ESP-IDF guide](https://docs.waveshare.com/ESP32-P4-WIFI6-Touch-LCD-3.5/ESP-IDF) still describe DSI for display examples. The product specification and BSP identify the integrated panel as SPI. Do not reuse another board's display clock/pin/driver setup. Camera CSI is a separate path.
3. **Two firmware components for networking.** A P4 image does not automatically update the C6. ESP-Hosted requires matching transport/configuration on both sides. Verify handshake, C6 version, association, DHCP, and traffic before combining UI and cloud features. [Espressif's getting-started guide](https://github.com/espressif/esp-hosted-mcu/blob/main/docs/getting-started-mcu.md) explains this boundary. New ESP-Hosted 3.x APIs are not interchangeable with the proposed 1.4/0.14 baseline pair.
4. **A build is not a hardware test.** The manufacturer's CI explicitly does not prove display/touch/wireless operation. P4 artifacts do not include C6 firmware. Physical checks remain necessary; simulator results cannot stand in for board evidence. [Official CI guide](https://raw.githubusercontent.com/waveshareteam/ESP32-P4-WIFI6-Touch-LCD-3.5/main/docs/ci.md)
5. **UI concurrency.** The BSP requires display locking for LVGL calls outside its protected context and explicit backlight activation. Separate download/validation from UI work. [BSP header](https://raw.githubusercontent.com/waveshareteam/Waveshare-ESP32-components/master/bsp/esp32_p4_wifi6_touch_lcd_3_5/include/bsp/esp32_p4_wifi6_touch_lcd_3_5.h)

Reference pins from that BSP header; prefer its APIs over duplicating pin definitions:

| Signals | GPIOs |
| --- | --- |
| I2C SDA / SCL | 7 / 8 |
| LCD MOSI / clock / CS / DC | 20 / 21 / 23 / 26 |
| LCD reset / backlight | 27 / 28 |
| Touch reset / interrupt | 29 / 50 |
| I2S MCLK / SCLK / WS / DOUT / DIN | 13 / 12 / 10 / 9 / 11 |
| Amplifier enable | 53 |
| microSD D0 / D1 / D2 / D3 / CMD / CLK | 39 / 40 / 41 / 42 / 44 / 43 |

The initial research left C6 SDIO pins to be checked against this board's schematic and Wi-Fi example configuration; see the ledger for subsequent verification. Do not import a different Waveshare P4 pin map. The initial path can omit microSD, board camera, and embedded audio.

## App installation alternatives

| Approach | Verified evidence | Hackathon-day assessment |
| --- | --- | --- |
| JSON + action interpreter + LVGL | BSP provides LVGL rendering; our format/runtime must be built | Recommended: a small server/device validation contract, no compiler needed per generated app |
| Lua | Espressif publishes an ESP-IDF Lua component | Possible extension, but requires LVGL bindings, resource/execution limits, and controlled APIs; it is not already an app platform for this board |
| WASM | ESP-WASMachine lists P4 and P4 Function EV Board support | More expressive; adapting the Waveshare BSP, ABI, tools, and module lifecycle adds work before proving the happy path |
| Generated C/C++ firmware and OTA | ESP-IDF supports firmware OTA and rollback | Technically possible, but every app requires build, flash, reboot, and compatibility testing. Defer; future OTA can update the runtime itself |

Sources: [Espressif Lua](https://components.espressif.com/components/espressif/lua/versions/5.5.0/readme), [ESP-WASMachine](https://github.com/espressif/esp-wasmachine), [ESP-IDF P4 OTA](https://docs.espressif.com/projects/esp-idf/en/stable/esp32p4/api-reference/system/ota.html). These sources establish technology availability, not tested compatibility with the user's board.

## Runtime contract and hardware budgets

The canonical fields, widgets, actions, limits, and protocol live in [docs/04-contracts.md](../04-contracts.md). Do not maintain another schema here. Generator and firmware must share its fixtures; capability extensions first update that contract and pass G1.

Firmware-specific notes:

- Measure internal heap, PSRAM, and stack during parsing, UI construction, and package switching. JSON byte size does not measure parsed-object and LVGL memory; the peak may include both old and new views.
- Keep countdown/score updates in RAM. Persist packages according to the contract, without flash writes for every tick or tap.
- Test rapid taps on the physical display: one gesture must produce one event, avoiding duplicate press/release callbacks. The 10-second game needs a monotonic deadline and deterministic timeout/tap ordering.
- Keep a shell/recovery route reachable. Interrupted-download/activation and reboot tests must establish that the previous package remains usable.
- Board camera, battery, and microphone must not block phone-based generation. Start bring-up on USB power for logs and immediate recovery.

## Proposed companion-to-device connection

Phone and board use the same backend; the board opens outbound connections. The companion selects a paired device. **Generate and install** binds the job to it and authorizes automatic publication after validation. The P4 polls HTTPS, downloads the package, and reports its result. The phone browser does not need to reach an HTTP server on the microcontroller. Pairing and deployment details remain in the [canonical contract](../04-contracts.md).

Preconfigure demo Wi-Fi credentials outside the repository and use a **2.4 GHz** network/hotspot, as required by the [board Wi-Fi guide](https://docs.waveshare.com/ESP32-P4-WIFI6-Touch-LCD-3.5/ESP-IDF). Keep model credentials in the backend; the device only needs its own scoped, revocable token. TLS requires hostname/certificate verification and a usable clock. BLE pairing, access-point provisioning, and P4 video upload are later extensions.

If C6 networking blocks bring-up, a disclosed technical fallback is the same package/validator over USB-UART through the laptop. This allows runtime progress but does not prove the wireless happy path.

## Launch gates and completion evidence

| Gate | Evidence required before proceeding |
| --- | --- |
| H0 — identity and recovery | Confirmed physical model, probed silicon revision, correct USB port, 16 MB flash, known BOOT/RESET procedure, recorded recovery baseline |
| H1 — BSP | Display/touch example on the board; correct orientation; taps in every corner; no reboot loop |
| H2 — network | Identified C6 firmware; DHCP; backend request; complete download; reconnect after Wi-Fi interruption |
| H3 — local runtime | Shared hand-authored acceptance fixtures demonstrate navigation, timer, and score; invalid package rejected |
| H4 — installation | A → B without reflashing; correct ACK; reboot reloads package; interrupted download preserves A; duplicate delivery preserves running state |
| H5 — generation | Android companion prompt → one Generate and install action → validated spec → interactive P4 app; no manually prepared app code substituted for that input |
| H6 — demo rehearsal | Three full runs with fresh input, recorded timing, tested recovery, clearly labeled backup video |

Proposed timebox: if H1/H2 are not green after 60–90 minutes of actual hardware work, stop adding peripherals and resolve the blocker. Do not spend that period on embedded camera, Brookesia, or WASM. This is an operational budget, adjustable once the actual hackathon duration is known.

## Remaining assistant-owned probes

Use [readiness](../11-readiness.md) for the current state, then record gate evidence in [the work ledger](../12-work-ledger.md).

1. Identify the connected USB interface and read silicon revision/boot information. Do not ask again for the board model or physical connection already provided.
2. Inspect the installed firmware and preserve a recoverable baseline; test display/touch/network when the toolchain is ready. Ask about an existing custom project only if its presence would change the recovery approach.
3. Establish exact IDF/esptool versions and component locks. The assistant owns installation and compatibility research.
4. Check the chosen Mac Wi-Fi for 2.4 GHz support, obtain provisioning data through an authorized route and test association/backend reachability. Ask for an alternative network only after a concrete incompatibility.
5. Exercise the shared tap-game fixture: start, score during ten seconds, result and replay. Add no peripheral requirement without a concrete demo need.

These observations can change the technical baseline without expanding the first happy path.
