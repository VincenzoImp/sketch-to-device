# Product and main user journey

## Value proposition

A person who can describe an interaction but cannot program turns a sketch and spoken explanation into a working app on a small physical device. The demonstration must show that the input determines both the interface and its behavior.

The proposed benefit is a dedicated object available on a desk or workbench, with large touch controls and one activity at a time. This is a product hypothesis, not completed user research. A simple game is an acceptable demonstration of the creation mechanism.

## Required main experience

**One prompt → one Generate and install action → a working app appears on the paired device.**

Pair the Android companion and device during setup. The main demonstration does not depend on a clarification exchange, transcript confirmation, preview approval, editing the prompt or generating a second revision. All visible text and spoken demo input are English.

1. The companion shows the already paired target device. Pairing setup can use the code displayed by the device.
2. The user supplies one short video showing a sketch and explaining the app, or a sketch photo with speech. Text is a supported development/fallback input; the main two-partner demonstration includes speech processed by Gradium.
3. The user presses **Generate and install on [device]** once. This authorizes generation and deployment of a validated, reversible app package to that target.
4. Gradium transcribes the speech; Gemini interprets the visual material and request. The system resolves nonessential ambiguity using documented defaults. A transcript or brief can appear as passive progress information, with no confirmation required.
5. The agent creates the app and runs real validation and behavior checks. Bounded repair attempts happen automatically. Progress reflects real job events.
6. After independent backend validation, the package is delivered automatically. An optional preview may appear in parallel, without blocking deployment.
7. The device validates and activates the package, then acknowledges its app ID, version and hash. Only then does the companion report **Installed**.
8. The user interacts with the requested app on the touchscreen. The previous valid app remains recoverable.

If the request cannot be fulfilled within the supported runtime, show a clear failure without activating a partial app. The happy path uses a complete prompt within those capabilities. Do not invent a mandatory conversation step to compensate for missing implementation.

## Candidate demo: a 10-second tap game

The candidate app is **Tap Sprint**:

- **Start screen:** title, short instruction and Start button.
- **Play screen:** a large Tap button, score and remaining time.
- **Behavior:** starting resets score to zero and starts a 10-second timer; each tap during play increments score; expiry transitions to the result screen.
- **Result screen:** final score and Play again button, which starts a fresh round.

Suggested one-shot English prompt, with a matching sketch:

> Create a game called Tap Sprint. Show a Start button. When I start, give me ten seconds to tap a large button as many times as possible. Show my score and remaining time. At zero, show my final score and a Play again button. Use a dark background and a bright green tap button.

The runtime must already support the declared actions and timer events. Validate zero taps, multiple taps, expiry, taps after expiry and restart. The score and timer are local device behavior; they must keep working after the network disconnects. This candidate does not imply physics, arbitrary animation or unrestricted game code generation.

Hold the sketch still for several seconds. Aim for a 15–30 second recording; shorter recordings are accepted. The source [canonical contract](04-contracts.md) allows audio up to60seconds, video up to30seconds,20MiB per file and32MiB combined; the running service must be restarted to adopt source changes. The game's 10-second round is a separate setting.

## Priorities

These priorities describe the selected working implementation. [Decision D06](10-decisions.md) records why the companion is a mobile web app; this is an implementation choice, not a claim that the user mandated a particular framework. Technical choices still require the stated probes.

| Level | Capability |
| --- | --- |
| P0 | Android mobile web companion with one complete request and one Generate and install action |
| P0 | Sketch plus speech, including short video with audio; actual Gemini and Gradium calls |
| P0 | Agent tool execution, validated package, automatic reversible delivery and activation acknowledgment |
| P0 | Touch controls, score/state, timer and navigation needed by the candidate demo |
| P0 | Previous valid app remains recoverable; failure preserves the running app |
| P1 | Conversational revisions, editable transcript, optional questions and interactive preview |
| P1 | In-page recording if verified on the actual Android browser; native camera/gallery upload is sufficient initially |
| P1 | A library of two or three installed apps with a device selector |
| P1, after physical one-shot acceptance | Apps that invoke AI while running, through a bounded backend operation; user suggested this extension during implementation |
| P2 | PDFs, multiple attachments, translation, animations and device-speaker audio |
| P2 | Input captured directly with the ESP32 camera and microphone |

The first engineering slice can be text → package → device. Voice and visual input then complete the main two-partner demonstration. A text-only fallback without a tested, app-specific Gradium TTS call does not prove both partner integrations; even with TTS, it does not demonstrate multimodal input.

## Implemented baseline and expanded product direction

The deployed firmware runs a fixed declarative format with screens, touch controls, variables and timers. That was an implementation choice for the initial proof. The user now requires broader real app programming, with consultable SDK documentation and device features; the earlier P1/P2 priorities above describe the initial rollout, not a prohibition on that work. [Programmable apps and the device platform](15-programmable-apps.md) owns the new direction, runtime comparison, shell design and implementation gates. A JavaScript engine does not imply Android or browser compatibility.

Generation and updates require remote services; local actions continue offline after installation. The confirmed camera and battery are available hardware, but acquisition begins on the Android phone in the MVP.

## What makes the demo convincing

- A new sketch and spoken request visibly affect layout and behavior.
- One explicit action produces an installed app without a manual approval chain.
- Real agent tools produce observable validation results and a usable artifact.
- The device actually executes the app and acknowledges the installed version.
- Gradium and Google DeepMind are credited beside the work each performs; timings and provider activity can be shown without secrets.

Avoid claims of absolute novelty without dedicated research. A specific, understandable and working demonstration is the priority.

## Context for the app-building agent

Every generation receives the implemented schema, runtime capabilities, trusted validator/reference runtime, user prompt and supported media. The managed agent must produce an artifact and run the supplied check. The backend downloads the actual bytes and independently repeats validation and behavior checks; a prose claim of success is insufficient. See [generation implementation](../backend/generator.py) and [current evidence](research/managed-probe.md).

AI-powered behavior inside a generated app is feasible through a future backend broker. Provider keys remain server-side; a permitted app action would request a constrained operation and display a bounded result with loading/error states. Runtime v1 currently has no network/AI action or dynamic text state. Do not advertise an Ask AI button as working intelligence or silently substitute a static answer. The user has reopened this area alongside the programmable runtime; it still needs an implemented broker and tested capability contract.
