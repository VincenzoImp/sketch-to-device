# Gemini: verified integration research for device app generation

Historical research date: **10 October 2026**, before authenticated API probes and implementation. API examples below were documentation-verified shapes, **not executed examples**. Assertions about untested access and prerequisites describe that initial research stage. Subsequent live results belong to [provider probes](provider-probe.md), [managed execution](managed-probe.md), [readiness](../11-readiness.md) and [the work ledger](../12-work-ledger.md).

The [implemented architecture](../03-architecture.md) supersedes the proposed SDK, separate multimodal/ConceptBrief stage and video Files API path below. The current worker uses REST, managed-agent inline images, one extracted video frame and Gradium speech, with independent trusted AppSpec checks. The old smoke-test list is research history, not a requirement to introduce those superseded stages or repeat completed probes.

## Proposed integration

Use **Gemini 3.8 Flash** to interpret visual material and the user's request, and **Antigravity managed agent** to produce an `AppSpec`, execute validation tools and repair errors. Gradium supplies the speech transcript. The backend independently validates the artifact and automatically delivers it to the paired device under the user's single **Generate and install** action. Deployment is bounded and reversible; preserve the prior valid app.

The main demo is one complete prompt followed by a working app on the device. It requires no clarification exchange, transcript confirmation, preview approval or second revision. An optional preview can appear in parallel. All project documents, prompts, interface text and generated demo content are English. Android is the confirmed companion platform; **Gradium + Google DeepMind** is the user's preferred partner combination.

The firmware remains a stable native runtime. AI generates screens, widgets, variables and supported actions in a constrained declarative format. This is our proposed architecture, not an existing Gemini feature. The candidate is a 10-second tap game with start, score, timer and result, provided those capabilities are implemented in the runtime contract.

The supplied event brief asks for real users, agents that complete work, human control of irreversible actions and a live 20:00 demo. The sequence **interpret → build → test → repair if needed → install a validated app** provides observable agent behavior. The generation button authorizes the specific reversible app deployment, not firmware flashing or unrelated external actions.

## Models and SDKs

Official documentation confirms the brief's `gemini-3.8-flash` and `antigravity-preview-09-2026` identifiers. The official skill specifies **Python `google-genai >=2.25.0`** and **TypeScript `@google/genai >=2.3.0`**. The brief's generic 2.3.0 minimum should not be applied to Python. Earlier `google-generativeai` and `@google/generative-ai` packages are deprecated. Current responses expose `steps` and the `output_text` convenience accessor; avoid old `outputs` examples. No skill was installed globally. [Official Gemini API skill](https://github.com/google-gemini/gemini-skills/blob/main/skills/gemini-api-dev/SKILL.md)

**Implementation gate:** select and lock a concrete SDK version after the first smoke test. Documentation availability and access from the hackathon account are separate checks.

## Media: Android phone → providers → brief

Video inputs use a `type: "video"` block with an uploaded file `uri` and `mime_type`, or inline base64 `data`. MP4 and WebM are documented. Video understanding also includes audio. Default static visual sampling is 1 FPS, so hold the sketch steady for several seconds. Agentic video processing exists but may add latency for short clips. The page contains conflicting size guidance: its table allows inline below 100 MB, while its prose recommends Files API above 20 MB. **Project choice:** use Files API for every video and begin with static processing. [Video understanding](https://ai.google.dev/gemini-api/docs/video-understanding)

The [canonical product contract](../04-contracts.md) caps recordings at 30 seconds and attachments at 20 MiB. A 15–30 second clip is guidance, not a minimum; shorter clips are accepted. These are project budgets, not provider limits. The candidate game's 10-second round is unrelated to recording duration. Verify the actual Android browser's output format; do not assume every phone produces the same codec/container.

Files API exposes `client.files.upload(file=...)`, `get(name=...)` and `delete(name=...)`. Wait for `ACTIVE`; stop on failure or timeout. Uploaded media expires after 48 hours. The guide states 2 GB per file and 20 GB per project, which are unnecessary for this MVP. User-uploaded media cannot be downloaded back through Files API; preserve originals in application storage when session recovery needs them. [Files API](https://ai.google.dev/gemini-api/docs/files)

Separate audio uses `type: "audio"` with `uri` or `data` and `mime_type`; documented formats include WAV, MP3, AAC, OGG, FLAC, M4A, Opus and WebM. Our preferred speech transcript comes from Gradium and enters the brief as text. If Gemini also hears the video audio, preserve source attribution and resolve conflicting interpretations instead of silently merging them. [Audio understanding](https://ai.google.dev/gemini-api/docs/audio)

Proposed `ConceptBrief`: target user, requested behavior, screens, actions, local data, explicit constraints, assumptions and attachment references. Distinguish user statements from visual observations and system defaults. For the main path, resolve nonessential ambiguity using supported defaults; record assumptions passively without demanding confirmation. An unsupported or unusable request fails clearly before activation. The chosen demo prompt must be complete and within the runtime's capabilities.

## Context and structured output

`previous_interaction_id` continues a conversation. `tools`, `system_instruction` and `generation_config` must be supplied again on each turn. Storage is enabled by default; the guide lists 55-day paid-tier and one-day free-tier retention. `store=false` prevents ID-based continuation and background execution. Provider retention does not replace our application database. [Interactions overview](https://ai.google.dev/gemini-api/docs/interactions-overview)

**Project design:** store the submitted request, media references, brief and job version on the backend. Generate and install freezes this snapshot. Later messages must not modify an active job. Conversational revisions are P1; they are not needed to complete the main demo.

Current schema-constrained output uses `response_format` with `type: "text"`, `mime_type: "application/json"` and `schema`. Official examples support Pydantic and Zod. Only a JSON Schema subset is supported; very large or deeply nested schemas may be rejected. [Structured outputs](https://ai.google.dev/gemini-api/docs/structured-output)

Adapted, **untested** API shape; `brief_schema` is a project-owned schema still to be written:

```python
brief_turn = client.interactions.create(
    model="gemini-3.8-flash",
    input=[
        {"type": "video", "uri": uploaded.uri, "mime_type": uploaded.mime_type},
        {"type": "text", "text": "Extract the app brief using supported defaults."},
    ],
    response_format={
        "type": "text", "mime_type": "application/json", "schema": brief_schema
    },
)
```

Valid JSON does not establish correct behavior. Application validation must reject unreachable screens, duplicate IDs, invalid transitions, unsupported widgets/actions, out-of-range values and packages incompatible with the runtime version.

## Managed agent: concrete role and input limitation

Antigravity currently accepts direct **text and image** inputs, with images supplied as inline base64. Do not assume it accepts the same audio/video inputs as the model. Available tools include code execution, filesystem, search and URL access; supplying `tools` customizes the set. `agent_config.max_total_tokens` limits an interaction; exhaustion can return `incomplete`. The agent is in preview on free and paid tiers, with costs determined by tokens and tools. [Antigravity agent](https://ai.google.dev/gemini-api/docs/antigravity-agent)

**Design consequence:** send a normalized textual brief and runtime constraints to a fresh managed-agent interaction. Do not automatically chain the complete multimodal conversation through `previous_interaction_id` without testing compatibility.

The quickstart distinguishes two state dimensions: `previous_interaction_id` preserves conversation context, while `environment=interaction.environment_id` preserves files and installed packages. Use both for repair turns. A new `environment="remote"` provisions a new workspace. [Managed agents quickstart](https://ai.google.dev/gemini-api/docs/managed-agents-quickstart)

Proposed sandbox inputs:

- `runtime-contract.json`: actual firmware capabilities, display dimensions and measured limits.
- `app.schema.json`: versioned `AppSpec` contract.
- `validate_app.py` and behavior fixtures authored and verified by us.
- `brief.json`: immutable user-request snapshot.
- Small approved examples that use only implemented runtime features.

The agent creates `out/app.json`, runs validation and interaction scenarios, reads failures, repairs the app, reruns checks and writes `out/validation.json`. Evidence includes commands, exit codes and the tested artifact's hash. The backend reruns its trusted validator on the downloaded artifact: the agent's written report alone is insufficient, and modifying sandbox tests cannot make an invalid package deployable.

For the tap-game candidate, verify score reset, score increments, timer expiry, rejected taps after expiry and restart. The agent may repair the generated app within the job budget without a user conversation. Backend delivery follows successful checks automatically under the original Generate and install authorization.

## Artifacts and sandbox

Current APIs include `client.environments.files.list(environment=..., path=..., recursive=True)` and `client.environments.files.download(environment=..., path=...)`. Listing paths are relative to the environment root; use returned paths to download `app.json` and its report. Environments documentation explicitly deprecates `/files/environment-{id}:download`, although the quickstart still shows that legacy endpoint. Prefer the new API. Inline sources are limited to 1 MB each and 2 MB total; inactive environments expire after seven days. `network="disabled"` blocks outbound access; a domain allowlist is also available. [Agent environments](https://ai.google.dev/gemini-api/docs/agent-environment)

Download named artifacts instead of treating final prose as the app. Enforce size bounds and validate encoding, JSON, schema and hashes before placing them in application storage. The MVP does not need to download and extract the entire sandbox archive.

The brief's official skill repository can be mounted as a repository source. For this specific app format, the runtime contract is the essential generation input. Record contract versions and hashes. Never place provider keys in prompts, attachments, the Android client or device firmware.

## Job loop, tools and interruption

The API reference includes `queued`, `in_progress`, `requires_action`, `completed`, `failed`, `cancelled` and `incomplete`; the skill's short list omits some states. Keep the interaction ID and current status. An unknown state must not be interpreted as success. The reference documents `background`, interaction retrieval and `steps`. [Interactions API reference](https://ai.google.dev/api/interactions-api)

Proposed backend behavior:

| Status | Action |
| --- | --- |
| `queued`, `in_progress` | Poll every 2–5 seconds with a job deadline and real progress events. |
| `requires_action` | Validate arguments, execute only registered local functions and return results. |
| `completed` | Download artifacts, independently validate and continue authorized deployment. Preview is optional. |
| `incomplete` | Preserve work; allow at most one continuation within the whole-job budget. |
| `failed`, `cancelled` | Preserve the running device app; report the problem and allow an explicit retry. |
| Unknown state | Record an API contract error and stop delivery. |

`background=True` enables polling with `client.interactions.get(id=...)` and requires storage. Function-call steps carry `id`, `name` and `arguments`; responses use `function_result` linked by `call_id`. Execute only outstanding calls rather than rerunning calls already matched by a result. One documented `result` shape is an array of text blocks containing serialized JSON. Resupply required tools on subsequent turns. [Function calling](https://ai.google.dev/gemini-api/docs/function-calling)

Possible project tools are `validate_app`, `simulate_action_sequence` and `render_preview`. Validation must execute our real code; simulation must produce observable states. Running the same tools through the sandbox CLI is sufficient if that provides the simpler integration.

Webhooks offer interaction completion, failure and cancellation events. Verify signatures and handle retries idempotently. **MVP choice:** provider polling plus backend-to-companion progress events. Webhooks are deferred to reduce public endpoint setup. [Webhooks](https://ai.google.dev/gemini-api/docs/webhooks)

## Quotas, cost and account availability

Quotas apply per project, not per API key. They include requests/minute, input tokens/minute and requests/day, varying by model and tier. Actual account limits are visible in AI Studio and cannot be inferred from the event brief. The provider also documents spend-window limits and `429 RESOURCE_EXHAUSTED`. Do not promise app throughput or latency based on model names alone. [Rate limits](https://ai.google.dev/gemini-api/docs/rate-limits)

Proposed initial controls: one active generation per user/device, no more than two application repair attempts, a token budget and a global deadline. Measure upload, understanding, agent execution, download, validation and installation separately. Bound transient retries with backoff; make delivery idempotent. A repair loop needs an explicit time/cost limit and a clear failure outcome.

## Required smoke tests before the long implementation pipeline

These checks require the authorized accounts and have **not been run**:

1. **SDK/model:** make a minimal text request with the selected model; record SDK version, final status and `output_text`. Resolve authentication/access errors instead of substituting fixture results.
2. **Multimodal:** record a real 15-second sketch-and-speech clip on the Android phone. Confirm that visible material and spoken instructions both influence the brief, and that the actual media format is accepted.
3. **Schema:** obtain a valid `ConceptBrief`; verify a small schema before the complete contract. Do not silently hand-edit a model result during the demo.
4. **Managed agent:** create a known file, run a real command/test, await completion and download the file through Environment Files API. Verify bytes and hash.
5. **Repair:** provide an app with a deliberately invalid transition; require a real validation failure, automatic repair and successful rerun.
6. **Resume/cancel:** continue with both IDs and verify file persistence. An interrupted job must not become a fake success.
7. **One-shot delivery:** one Generate and install action leads to an acknowledged package and a working device app, without transcript or preview confirmation. Verify app/version/hash and persistence after restart.
8. **Partners:** Gradium processes real speech and Gemini constructs the app in the same flow. Text-only input without a tested, app-specific Gradium TTS call does not prove both integrations. Even with TTS, text-only input does not demonstrate visual or spoken input understanding.

## Declared fallbacks and remaining unknowns

- If managed-agent access is unavailable, use Gemini with local validation tools and a bounded tool/repair loop. Confirm with mentors whether managed agents are mandatory or recommended for the track.
- If video input fails, use a sketch photo plus Gradium speech transcription. Clearly describe this reduced capability instead of claiming successful video understanding.
- If connectivity or quota fails, a previously generated, validated package can demonstrate the runtime. Label any non-live portion explicitly.
- Remaining tests: configured-key authentication and credits, managed-agent access, exact Android browser/media behavior and job latency. Hardware model, USB connection, network choice, phone platform, English demo and partner preference are already established; silicon and physical operation need separate probes. The [readiness register](../11-readiness.md) owns their current status.

The main APIs are documented, but **account availability, latency and combined compatibility remain unmeasured**. The first four smoke tests gate substantial development depending on these services.
