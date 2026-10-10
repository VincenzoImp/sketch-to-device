# Sketch to Device

Operating context for the Agentic AI Hack Zürich on October 10, 2026. Turn a short description or a narrated sketch into an interactive app on a Waveshare ESP32-P4 device. Working project name.

**Current phase: implement the reviewed programmable generation platform.** The user will supply the prompt and image; Gemini must author the app, without prepared game templates or coordinator-written substitutes. [The revised platform plan](docs/16-final-platform-plan.md) defines the rewrite, SDK, Google AI Studio/Pi assessment and staged proofs. The user has activated implementation of that plan (D30); new capabilities require their own practical proofs. Production remains AppSpec0.2: voice, photo-only and Hello Colors worked physically; Flappy Bird exposed its limitations. A plan or compiled probe is not a deployed capability.

## Primary experience

On an Android phone, the user supplies one prompt, optionally with a sketch, voice recording, or short video, then taps **Generate and install** for an already paired device. Gradium handles the spoken input. Gemini interprets the request, uses tools to build and validate an application package, and sends it to the device. After the device acknowledges the exact installed version, the user can interact with the app on its touchscreen.

This action authorizes the reversible installation of the validated package. Transcript confirmation, preview approval, and another chat turn are not required. An optional preview can show progress; conversational revisions are a later enhancement. A candidate live demonstration is a simple 10-second tap game generated from one English prompt.

The implemented firmware is a reusable ESP-IDF/LVGL runtime for the **Waveshare ESP32-P4-WIFI6-Touch-LCD-3.5**. It currently executes a bounded JSON AppSpec, without compiling firmware for each app. This format has real expressive limits: it is not arbitrary application programming. Isolated QuickJS-NG engine and real LVGL UI probes now pass host checks, and the isolated UI adapter cross-compiles for P4. A versioned production UI/device SDK and physical integration remain the next gates. Existing apps remain supported during that work. Camera, microphone and speaker APIs for generated apps are not implemented yet.

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

The [versioned agent SDK](agent-sdk/README.md) packages consultable API references, managed-agent instructions/skills and runnable examples for the currently implemented runtime. The [platform exploration](docs/15-programmable-apps.md) records alternatives/probes; the [release plan](docs/16-final-platform-plan.md) reconciles the audit and defines the shared capability and acceptance gates.

The new [programmable SDK](agent-sdk/program-v1/README.md) and [shared native core](firmware/program_core/README.md) are separate implementation candidates. Their source and host checks do not advertise availability on the currently installed device.

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

The reviewed update adds button colors, input normalization, larger media bounds and phase timing. The service was restarted and runtime0.2 flashed on10October. Fresh Hello Colors reached exact sequence12 activation and user-confirmed color cycling. The following Flappy Bird request was refused as unsupported and preserved that app. The new programmable engine remains a separate feasibility probe, not part of that production firmware.

The selected partners are **Google DeepMind and Gradium**. Entire is optional and parked. All project artifacts, UI, code comments, agent prompts, and demo material must be in **English**; the conversation with the user remains in Italian.

**Deadlines:** public competition opt-in at 19:00; the user's ready-by target at 17:00; live demos at 20:00, all Europe/Zurich. See [event details](docs/01-event.md).

The verified public checkpoint preceding this redesign revision is [d223469](https://github.com/VincenzoImp/sketch-to-device/commit/d223469e89f2fca6057ff97c01598fa02ede3c53), containing158 reviewed files and preserving earlier commits. The coordinator published it directly after full access became available and matched all committed file hashes and remote main. The redesign plan was subsequently published and verified at5a183fd; source publication does not update the running service or device. Use [checkpoint_github.py](scripts/checkpoint_github.py) for authorized follow-up commits: it audits the public tree, pushes without force and verifies the remote. Original PDFs, `.env`, private media and credentials remain excluded. The initial100-file export hash belongs only to its historical snapshot, recorded in the ledger.

To check the public context and current source allowlist, run `python3 scripts/check_context.py --export`. This validates local document links and scans known credential signatures/configured secret values; it does not test the app or prove GitHub publication. The snapshot is written to ignored `artifacts/context-public.tar.gz`. Unlisted future source types and Git history need separate review before publication.
