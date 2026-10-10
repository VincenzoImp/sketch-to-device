# Sketch to Device

Operating context for the Agentic AI Hack Zürich on October 10, 2026. Turn a short description or a narrated sketch into an interactive app on a Waveshare ESP32-P4 device. Working project name.

**Current phase: broaden app programming while preserving the working demo.** A voice-generated app and a separate photo-only app have been installed and used on the physical device. The voice app also survived an ordinary reboot; its requested title was misrecognized. The user has now prioritized a programmable runtime, consultable agent SDK and broader device APIs. See [the platform decision and feasibility gates](docs/15-programmable-apps.md) and [current evidence](docs/12-work-ledger.md). Local source improvements and a compiled binary are not automatically deployed or published.

## Primary experience

On an Android phone, the user supplies one prompt, optionally with a sketch, voice recording, or short video, then taps **Generate and install** for an already paired device. Gradium handles the spoken input. Gemini interprets the request, uses tools to build and validate an application package, and sends it to the device. After the device acknowledges the exact installed version, the user can interact with the app on its touchscreen.

This action authorizes the reversible installation of the validated package. Transcript confirmation, preview approval, and another chat turn are not required. An optional preview can show progress; conversational revisions are a later enhancement. A candidate live demonstration is a simple 10-second tap game generated from one English prompt.

The implemented firmware is a reusable ESP-IDF/LVGL runtime for the **Waveshare ESP32-P4-WIFI6-Touch-LCD-3.5**. It currently executes a bounded JSON AppSpec, without compiling firmware for each app. This format has real expressive limits: it is not arbitrary application programming. Isolated QuickJS-NG engine and real LVGL UI probes now pass host checks, and the engine alone cross-compiles for P4. A versioned production UI/device SDK and physical integration remain the next gates. Existing apps remain supported during that work. Camera, microphone and speaker APIs for generated apps are not implemented yet.

## Read in this order

**New session or subagent:** first read [AGENTS.md](AGENTS.md) and [session handoff](docs/09-session-handoff.md). The handoff gives a one-minute overview, role-specific reading paths and the source of truth for each question. Current work lives in [the work ledger](docs/12-work-ledger.md); distinguish it from the future implementation plan.

1. [Status and remaining prerequisites](docs/00-status.md)
2. [Event, deadlines, and accounts](docs/01-event.md)
3. [Product and primary experience](docs/02-product.md)
4. [Architecture and decisions](docs/03-architecture.md)
5. [Component contracts](docs/04-contracts.md)
6. [Execution pipeline and review gates](docs/05-execution-plan.md)
7. [Validation and demo](docs/06-validation-demo.md)
8. [Source index](docs/07-sources.md)
9. [Agent handoff and product prompt templates](docs/08-agent-prompts.md)

Operational references: [decision origins and history](docs/10-decisions.md), [access and readiness](docs/11-readiness.md), [task ownership and gate results](docs/12-work-ledger.md).

Every deliverable follows [independent review and practical verification](docs/13-quality-gates.md) and the [active research workflow](docs/14-autonomy-and-research.md). The implementation is not complete until the real Android → providers → physical device path passes acceptance.

Research: [hardware](docs/research/hardware.md), [Gemini](docs/research/gemini.md), and [partners](docs/research/partners.md). [AGENTS.md](AGENTS.md) governs subsequent work.

The [versioned agent SDK](agent-sdk/README.md) packages consultable API references, managed-agent instructions/skills and runnable examples for the currently implemented runtime. The [programmable platform plan](docs/15-programmable-apps.md) describes the separate engine and device-framework extension.

## Setup on the tested Mac and board

Run commands from the repository root in a normal macOS Terminal. The tested hardware is ESP32-P4 revision 3.2 with 16 MB flash; the flash helper checks that identity. The backend uses Python 3.9+ and the standard library, with no Python SDK or npm installation. Full hardware setup was tested with `python3` resolving to Python 3.9: the hardware helpers currently expect the IDF virtual environment named `idf5.5_py3.9_env`.

Have Apple command-line tools, Git, cloudflared, and FFmpeg/FFprobe installed first. The [firmware bootstrap](scripts/setup_firmware_tools.sh) installs the pinned IDF/P4 toolchain, CMake and Ninja, then builds the vendor example; it does not install those prerequisites or flash the board.

1. Copy the public key template without overwriting an existing configuration, then fill its two key values in a local editor:

   ```sh
   cp -n .env.example .env
   chmod 600 .env
   ```

   Gemini access must support the selected managed agent, environment tools and Files API; Gradium needs speech-to-text access and quota. Keep `.env`, private configuration and input media out of publication.

2. Build the tools/vendor baseline, then start the companion and HTTPS tunnel. Keep this terminal running:

   ```sh
   bash scripts/setup_firmware_tools.sh
   python3 -B scripts/run_demo.py
   ```

   The launcher verifies public HTTPS and opens a private QR/link page. It does not generate an app. The vendor build is required by the guarded flash helper; a separate vendor flash is not required.

3. Connect the board's serial USB port. In another terminal at the repository root, identify and provision it, then perform the first runtime flash:

   ```sh
   python3 -B scripts/identify_board.py --probe
   python3 -B scripts/provision_device.py
   python3 -B scripts/board_baseline.py --flash-runtime --initialize-app-storage
   ```

   Enter a network without a captive portal; the tested board uses an Android cellular hotspot, which can differ from the Mac's network. Enter its SSID explicitly instead of accepting the provisioner's Mac-network default. The flash helper builds the private configuration, backs up and verifies the original 16 MB, and initializes only the dedicated 512 KiB app-storage region on first setup. This operation can take several minutes.

4. Open the private QR on Android, provide an English concept or recording, and tap **Generate and install** once. Confirm the exact installation state and test the physical app. Keep the Mac service/tunnel and hotspot running.

For later firmware/configuration updates, use `--flash-runtime` without the initialization flag. A launcher restart can change the public endpoint: provision against the new running service while preserving network/device identity, then rebuild/flash before expecting delivery. Ordinary app generation installs an AppSpec package without flashing firmware. See [readiness](docs/11-readiness.md) before repeating setup in an existing workspace.

## Current executable foundation

[Contract tooling](contracts/README.md) contains the schema, bounded parser/validator, deterministic reference runtime and behavioral fixtures. It runs on Python 3.9+ without third-party dependencies. Its host tests do not establish physical rendering, firmware behavior or provider integration.

```sh
python3 -B -m unittest discover -s tests -v
python3 -B -m runtime.check contracts/fixtures/tap-sprint.json --scenario contracts/scenarios/tap-sprint.json
```

[Hardware probe evidence](docs/research/hardware-probe.md) records the access and chip checks. [Provider probe evidence](docs/research/provider-probe.md) distinguishes managed-session network restrictions from successful user-terminal authentication. [Managed generation evidence](docs/research/managed-probe.md) records actual downloaded apps and the limits of their verification. Use the ledger for independent review status and remaining integration gates.

The [backend](backend/README.md) contains the HTTP service, deployment store and managed generation worker; the [companion](companion/README.md) supplies the mobile flow. The [firmware](firmware/README.md) contains the C runtime and LVGL renderer. Voice sequence6 (Rocket Tata) and photo-only sequence7 (Star Tap) received exact active acknowledgments and user-confirmed physical behavior. A later Hello World color request failed at the provider without replacing Star Tap; its precise cause is not established. Fresh combined photo+voice, interrupted-install recovery and broader fidelity remain separate acceptance work.

Local changes add button colors, input normalization, larger media bounds and phase timing. The source runtime is0.2; the last confirmed flashed runtime is0.1. Upgrade firmware and restart the service coherently before treating those changes as a live result. The new programmable engine is a separate feasibility probe, not part of the current firmware.

The selected partners are **Google DeepMind and Gradium**. Entire is optional and parked. All project artifacts, UI, code comments, agent prompts, and demo material must be in **English**; the conversation with the user remains in Italian.

**Deadlines:** public competition opt-in at 19:00; the user's ready-by target at 17:00; live demos at 20:00, all Europe/Zurich. See [event details](docs/01-event.md).

The latest verified public checkpoint is [aab9796](https://github.com/VincenzoImp/sketch-to-device/commit/aab9796974e0bbb9b2a65b0bc6df88f4a5cb0f36), containing 135 audited files and preserving the initial commit [8826f2e](https://github.com/VincenzoImp/sketch-to-device/commit/8826f2edb8ab662cc2e524e4867661832c8d04cd). The independently accepted initial 100-file export has SHA-256 `01f3b33eaa2968d2b3ebe02e1df55934da414a82ad4de69df4484b0a7391b08b`; it is not an archive of the newer checkpoint. The user requests periodic reviewed commits. Use the independently reviewed [checkpoint helper](scripts/checkpoint_github.py) with `--publish --message "Short description"` for follow-up commits; it audits the public tree, pushes without force and verifies the remote. Subsequent local changes remain unpublished until that succeeds. Managed Git/network restrictions still require normal-Terminal publication. Original PDFs, `.env`, private media and credentials remain excluded.

To check the public context and current source allowlist, run `python3 scripts/check_context.py --export`. This validates local document links and scans known credential signatures/configured secret values; it does not test the app or prove GitHub publication. The snapshot is written to ignored `artifacts/context-public.tar.gz`. Unlisted future source types and Git history need separate review before publication.
