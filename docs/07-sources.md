# Source index and verification policy

Research date: **10 October 2026**. Prefer the exact primary documentation linked below and in each research note. Web pages on `main`, `master` and `stable` can change; record immutable commits and resolved package versions when implementation begins.

## Local evidence

The original files remain at the project root and are excluded from Git by `.gitignore`. Do not upload account material to provider agents or publish the email PDFs.

| File | Useful content | Handling |
| --- | --- | --- |
| `[External] Google DeepMind x {Tech_ Europe}_ Agentic AI Hack Zürich brief.pdf` | Track criteria, models, Interactions API, managed agents, examples | Primary event brief; summarized in event and Gemini notes |
| `Gmail - Builder Guide_ Agentic AI Hack Zürich.pdf` | Organizer’s direction toward managed agents and Interactions API | Private email; factual summary only |
| `How to use a temporary account for a hackthon_ [Shared externally].pdf` | AI Studio onboarding, temporary account lifetime, export and key handling | Instructions contain older examples; verify current SDK/model details |
| `Gmail - Agentic AI Hack Account Information.pdf` | Temporary account access | Credential-bearing; never copy into project context or logs |

The PDF extraction used macOS PDFKit locally. Text from the account PDF was not added to the repository. Source documents may retain their original language; all project-authored content is English.

## Event and partners

| Source | What it supports |
| --- | --- |
| [Official event page](https://luma.com/zrh-hack) | Schedule and named partners |
| [Organizer newsletter](https://blog.techeurope.io/p/mistral-is-hiring-like-a-cloud-provider-our-zurich-hack-upcoming-builder-events) | Event date and partner context |
| [Gradium documentation](https://docs.gradium.ai/guides/introduction) | Supported capabilities and languages |
| [Gradium recorded-file transcription](https://docs.gradium.ai/guides/speech-to-text-rest) | REST STT contract |
| [Gradium STT API reference](https://docs.gradium.ai/api-reference/endpoint/stt-post) | Body formats and parameters |
| [Gradium transcription settings](https://docs.gradium.ai/guides/transcription-settings) | Language configuration |
| [Gradium errors](https://docs.gradium.ai/guides/errors) | HTTP and in-stream failures |
| [Gradium REST speech output](https://docs.gradium.ai/guides/text-to-speech-rest) | Optional app-specific TTS |
| [Entire CLI](https://github.com/entireio/cli) | Optional development checkpoints, not device runtime |

Detailed account prerequisites, limits, error handling and integration choices: [partner research](research/partners.md). Public documentation does not establish that a particular account has credit or access.

## Google DeepMind integration

| Source | What it supports |
| --- | --- |
| [Official Gemini API skill](https://github.com/google-gemini/gemini-skills/blob/main/skills/gemini-api-dev/SKILL.md) | Current SDK conventions and model guidance |
| [Interactions overview](https://ai.google.dev/gemini-api/docs/interactions-overview) | Conversation state and interaction lifecycle |
| [Interactions API reference](https://ai.google.dev/api/interactions-api) | Request/response shapes and states |
| [Video understanding](https://ai.google.dev/gemini-api/docs/video-understanding) | Multimodal processing |
| [Files API](https://ai.google.dev/gemini-api/docs/files) | Media upload and lifetime |
| [Structured outputs](https://ai.google.dev/gemini-api/docs/structured-output) | Schema-guided output |
| [Antigravity agent](https://ai.google.dev/gemini-api/docs/antigravity-agent) | Managed execution and input constraints |
| [Managed agents quickstart](https://ai.google.dev/gemini-api/docs/managed-agents-quickstart) | Initial calls and environment continuity |
| [Agent environments](https://ai.google.dev/gemini-api/docs/agent-environment) | Source mounting and artifact download |
| [Function calling](https://ai.google.dev/gemini-api/docs/function-calling) | Real tool execution cycle |

Known inconsistencies between quickstarts, API references and SDK versions are recorded in [Gemini research](research/gemini.md). Resolve them with a tiny authenticated probe, then pin the working version. Do not combine incompatible snippets silently.

Executable probes and their evidence: [minimal provider access](research/provider-probe.md), [managed execution and artifact retrieval](research/managed-probe.md). Only actual results in those notes can establish account availability; research alone cannot.

## Hardware and browser

| Source | What it supports |
| --- | --- |
| [Waveshare board documentation](https://docs.waveshare.com/ESP32-P4-WIFI6-Touch-LCD-3.5) | Board components and interfaces |
| [Waveshare examples](https://github.com/waveshareteam/ESP32-P4-WIFI6-Touch-LCD-3.5) | Firmware starting points |
| [Silicon revision guide](https://raw.githubusercontent.com/waveshareteam/ESP32-P4-WIFI6-Touch-LCD-3.5/main/docs/revisions.md) | Incompatible revision profiles |
| [LVGL example manifest](https://raw.githubusercontent.com/waveshareteam/ESP32-P4-WIFI6-Touch-LCD-3.5/main/examples/esp-idf/08_lvgl_demo_v9/main/idf_component.yml) | Candidate dependency versions |
| [Wi-Fi example manifest](https://raw.githubusercontent.com/waveshareteam/ESP32-P4-WIFI6-Touch-LCD-3.5/main/examples/esp-idf/04_wifistation/main/idf_component.yml) | P4/C6 host stack dependencies |
| [ESP HTTP Client](https://docs.espressif.com/projects/esp-idf/en/stable/esp32p4/api-reference/protocols/esp_http_client.html) | HTTPS transport on ESP-IDF |
| [Browser camera/microphone](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia) | Secure context and permission requirements |
| [Recorder MIME negotiation](https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder/isTypeSupported_static) | Runtime format checks |
| [Native capture picker](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Attributes/capture) | Mobile capture hint and compatibility limits |

Further pin mappings and alternative runtimes are in [hardware research](research/hardware.md). Neither vendor CI nor the existence of a BSP proves this particular board works with the selected software.

## Development autonomy

The [autonomy playbook](14-autonomy-and-research.md) applies official guidance to this repository. Its investigation timeboxes and milestone process are project choices, not guarantees from a provider.

| Source | What it supports |
| --- | --- |
| [Long-running Codex experiment](https://developers.openai.com/blog/run-long-horizon-tasks-with-codex) | Durable specification, milestone checks and repair loops |
| [Instruction discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md) | AGENTS.md scope and loading behavior |
| [Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents) | Bounded delegation and parallel-edit risks |
| [Sandboxing](https://learn.chatgpt.com/docs/sandboxing) | Filesystem and command execution boundaries |
| [Approvals and security](https://learn.chatgpt.com/docs/agent-approvals-security) | Managed policy and approval layers |

These sources describe the development host, not Gemini product APIs or physical integration evidence.

## Evidence precedence

1. Latest explicit user choices govern scope, language, priorities and target deadline.
2. Event brief and official event page establish their respective event facts; preserve distinctions such as opt-in versus delivery.
3. Exact version source/API reference and observed smoke results govern implementation compatibility.
4. Proposed architecture and estimated timings remain proposals until tested.

Keep a source URL beside material factual claims. Keep test evidence beside claims of working behavior. Avoid copying whole documentation sites into the repository: focused notes, exact links, version locks and actual test outcomes make more reliable implementation context.
