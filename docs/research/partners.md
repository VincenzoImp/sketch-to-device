# Partners: integration contracts and demo evidence

Historical research verified on October 10, 2026 against the primary sources linked below, before provider authentication and implementation. Proposals and initial prerequisites here are not current task status. The [implemented architecture](../03-architecture.md), [work ledger](../12-work-ledger.md) and [readiness](../11-readiness.md) own subsequent choices and actual evidence; [provider probes](provider-probe.md) and [managed execution](managed-probe.md) record specific live results. TTS, streaming and Entire are research alternatives, not implemented partner contributions. No credentials or promotion codes are included.

## Selected integration

The user selected **Google DeepMind + Gradium** and confirmed an English demo. Gemini interprets the request and any sketch, uses tools to generate and validate an AppSpec, then deploys it to the paired device. Gradium transcribes spoken input. For a text-only request, a newly synthesized, app-specific spoken summary is the alternative substantive Gradium contribution. The exact demo path must pass a real call to both providers.

The main experience is a single prompt followed by **Generate and install**. That action authorizes the reversible installation of a validated package on the selected paired device. No transcript confirmation, preview approval, or second chat turn is required. An optional transcript or preview can remain visible while the job proceeds. Entire is optional and parked outside this path.

Gradium currently documents English, French, German, Spanish, and Portuguese for STT and TTS. Italian is not listed; `language: "any"` does not imply universal language support. The user's English-demo decision fits the documented capabilities. [Gradium introduction](https://docs.gradium.ai/guides/introduction)

## Event evidence

The [official event page](https://luma.com/zrh-hack) lists Google DeepMind and J floor as co-hosts, and Gradium and Entire as technology partners. It promises provider credits without publishing allocations or redemption steps. The public page inspected does not state a mandatory two-partner rule. Google DeepMind + Gradium is the user's project requirement and selected combination; there is no evidence-based reason to add an eligibility checkpoint to the build plan.

| Milestone | Time, Europe/Zurich | Meaning |
|---|---:|---|
| Competition opt-in deadline | 19:00 | Register for the competition before this time |
| User's technical deadline | 17:00 | Ready for demonstration; reserve 16:00–17:00 for practical testing |
| Live demos | 20:00 | Demonstrate the complete path with real input |
| Awards | 20:45 | Event schedule |

The date and partners are also confirmed by the [organizer's October 5 newsletter](https://blog.techeurope.io/p/mistral-is-hiring-like-a-cloud-provider-our-zurich-hack-upcoming-builder-events). The local brief asks for a useful agent that acts, uses tools, preserves human control, and works live; its suggested Google APIs and model identifiers require the separate Gemini research and an authenticated preflight.

## Practical partner matrix

| Partner | Proposed responsibility | Prerequisite | Observable evidence | Priority |
|---|---|---|---|---|
| Google DeepMind / Gemini | Interpret request and sketch; orchestrate AppSpec generation, checks, and bounded repair | Event account/key; accessible model and tool API | New input produces matching UI and behavior; actual tool trace; installed physical app | P0 |
| Gradium STT | Turn recorded explanation into requirements used by generation | Backend key; supported audio format; English recording | Spoken rule appears in transcript and affects the generated app | P0 for spoken demo |
| Gradium TTS | Read a newly generated app-specific summary or instructions | Same key; tested public voice; phone audio playback | Output describes the app just generated, including its actual parameters | Alternative partner path for text-only input |
| Entire | Connect development sessions and decisions to Git checkpoints | CLI and compatible hooks | Actual checkpoint connected to a code change | Optional, parked |
| J floor | Event venue | No product API identified | Event context | No integration planned |

This matrix describes the intended implementation, not completed integrations. A text-only Gemini request without a real Gradium call does not pass the selected-partner acceptance criterion. Do not use a generic prerecorded welcome message as evidence of a generated spoken summary.

## Gradium STT: simplest path for a recording

The [REST STT guide](https://docs.gradium.ai/guides/speech-to-text-rest) supports completed audio files through one HTTP request. This fits a short finished recording without browser streaming infrastructure.

| Field | Verified contract |
|---|---|
| Method and URL | `POST https://api.gradium.ai/api/post/speech/asr` |
| Authentication | `x-api-key` header from backend-only `GRADIUM_API_KEY` |
| Body | Raw audio-file bytes, not JSON or multipart sent to Gradium |
| Recommended Content-Type | `audio/wav` |
| Required query | URL-encoded `json_config`; use `{"language":"en"}` for the demo |
| Model selection | Query parameter `model`; documented default is `default` |
| Response | `application/x-ndjson`; `text`, `end_text`, possible `error`; completion when the body closes |

The [STT POST reference](https://docs.gradium.ai/api-reference/endpoint/stt-post) lists `audio/wav`, `audio/pcm`, `audio/ogg`, and `audio/opus`. WebM, MP4, M4A, and MP3 are not documented uploads for this endpoint. Changing only an extension or MIME type is insufficient. Its autogenerated JavaScript example uses `res.json()`, but the actual contract is NDJSON: parse lines and handle lines split between network chunks.

Proposed pipeline, with a product limit of 30 seconds per recording:

1. The Android phone uploads the recording to our backend and displays progress.
2. The backend retains the original for visual analysis and extracts mono, 16-bit, 24 kHz PCM WAV audio.
3. The backend sends the WAV to Gradium and assembles the transcript. Segment timestamps can align speech with the visual input.
4. The job automatically supplies the transcript, prompt, and visual material to generation. The transcript may be visible, but does not require confirmation. Treat it as untrusted user content, never as system instructions.
5. Gemini produces an AppSpec; validators and bounded repair run automatically; the already authorized package is installed on the paired device.
6. Missing or failed transcription produces an actionable error or an explicitly labeled fallback. Do not silently treat partial speech as a complete request.

A transcript edit or conversational revision is optional P1 work. The success criterion is a working app after one request, not a mandatory refinement conversation.

The 30-second limit is our proposed product constraint. Gradium documents sessions up to 3,000 seconds, WAV PCM at 16/24/32 bits, raw PCM, and Ogg-wrapped Opus. Bare PCM defaults to mono 24 kHz. [Official limits](https://docs.gradium.ai/guides/limits)

### Media conversion prerequisite

Example conversion for controlled temporary backend files, invoked as a process with separate arguments and a timeout:

```text
ffmpeg -nostdin -i input-video.mp4 -vn -ac 1 -ar 24000 -c:a pcm_s16le output-audio.wav
```

`-vn` excludes video; `-ac` and `-ar` set channel count and sample rate. Use backend-generated filenames, check for an audio track, and remove temporary files after processing. Do not concatenate upload names into a shell command. [FFmpeg documentation](https://ffmpeg.org/ffmpeg.html)

The initial local inspection did not find `ffmpeg` on PATH; that historical prerequisite is superseded by the installation and conversion evidence in [readiness](../11-readiness.md). Actual Android capture remains a separate check. An alternative is Web Audio capture to PCM with a browser-created WAV and a separate sketch image; test it on the actual phone. A `MediaRecorder` blob does not guarantee PCM or WAV output.

### Error handling and configuration

Gradium may return HTTP 500 with plain text for authentication or input errors. After streaming begins, an `error` NDJSON event can arrive under HTTP 200. Check both surfaces, avoid retrying invalid input unchanged, and do not mark a partial transcript complete. [Error contract](https://docs.gradium.ai/guides/errors)

`json_config.language` is required. Use `en`; use `any` only when the supported language is unknown. The settings page permits `delay_in_frames` 0–80 while the WebSocket guide states 7–55. Avoid unnecessary tuning for REST; if streaming is later added, 16 is documented in both. [Transcription settings](https://docs.gradium.ai/guides/transcription-settings), [WebSocket guide](https://docs.gradium.ai/guides/speech-to-text)

## Gradium TTS: text-only input and optional spoken result

Use `POST https://api.gradium.ai/api/post/speech/tts`, header `x-api-key`, and a JSON body containing `text`, `voice_id`, `output_format: "wav"`, and `only_audio: true`. The response contains audio bytes. TTS uses optional `model_name` in its body, whereas STT uses `model` in its query. [REST TTS guide](https://docs.gradium.ai/guides/text-to-speech-rest), [TTS POST reference](https://docs.gradium.ai/api-reference/endpoint/tts-post)

Proposed output for the candidate tap game: a short explanation reflecting the generated duration, scoring rule, and controls. Produce it from the validated AppSpec, not invented app capabilities. Synthesis belongs to the same generation job; it does not introduce another approval or block device installation behind an audio-playback prompt. Test browser playback after the initial user gesture, and provide an optional Play summary control if autoplay is unavailable. The physical-app success state still depends on the device ACK.

Use one verified public voice ID in configuration. Voice cloning and ESP32 speaker playback are outside P0. For the spoken-input demo, STT already provides the Gradium contribution; TTS can be omitted. For a text-only demo, real app-specific synthesis must succeed to claim both selected partners were used, even if playback remains optional.

## Streaming: documented extension

Gradium exposes `wss://api.gradium.ai/api/speech/asr`. Its protocol requires setup, ready handling, audio chunks, and end-of-stream. Recommended PCM framing is mono 16-bit at 24 kHz, 80 ms: 1,920 samples or **3,840 bytes** per chunk. [Streaming guide](https://docs.gradium.ai/guides/speech-to-text)

For browser WebSockets, the backend can obtain a single-use token from `GET https://api.gradium.ai/api/api-keys/token` using `x-api-key`. The browser uses `?token=...`, reads `expires_at`, and obtains a new token for reconnects. Never send the permanent key to the phone. This flow applies to WebSockets, not the REST authentication above. [Browser WebSockets](https://docs.gradium.ai/guides/browser-websockets)

The [official microphone recipe](https://docs.gradium.ai/guides/recipes/browser-microphone-stt) demonstrates Web Audio float-to-PCM16 conversion. It is reference material, not proof that our Android/browser combination works. Record, stop, and upload is sufficient for P0.

## Accounts, credits, and configuration

Both partner keys are configured in private `.env`. The managed session cannot reach the provider; a later user-terminal check confirmed authentication and available credits. This does not establish speech processing. No secret value is included here. [Readiness](../11-readiness.md) owns environment and access status; avoid asking for already-configured keys again.

- **Google:** the private local brief points to event onboarding and a temporary account. Verify the model and API route available to that account. Do not assume Google Cloud credits and Gemini Developer API billing are interchangeable.
- **Gradium:** the [official website](https://gradium.ai/) links to [Gradium Studio](https://studio.gradium.ai/). Account access, a key, and actual credits are required; private event-credit redemption steps were not available in the sources inspected. Keep `GRADIUM_API_KEY` on the backend. The Python SDK requires Python 3.10+; direct REST from TypeScript does not require that SDK. [Installation](https://docs.gradium.ai/guides/installation)
- **Preflight:** authenticated `GET https://api.gradium.ai/api/usages/credits` returns balance and plan information. Log configuration status, never the key or authentication headers. [Get Credits](https://docs.gradium.ai/api-reference/endpoint/get-credits)
- **Published usage:** the pricing page lists 45,000 free-tier credits and API access. STT uses 3 credits/second; TTS uses 1 credit/character. Thus a 30-second recording is approximately 90 STT credits, our calculation. Event credits and actual account limits still require verification. [Gradium pricing](https://gradium.ai/pricing)
- **Data location:** the default endpoint selects a nearby cluster without a residency commitment. Regional guarantees require the applicable plan configuration. Do not claim EU-only processing or zero retention based solely on the provider's location. [Data residency](https://docs.gradium.ai/guides/data-residency)

## Entire: optional and parked

Entire links agent sessions to Git checkpoints and documents Codex support. It can make development decisions inspectable, but does not generate the device app or validate its behavior. [Entire's Codex guide](https://entire.io/blog/getting-started-with-codex-in-entire-cli)

Enabling it installs Git and agent hooks. Checkpoints accompany commits and can be inspected with `entire status`, `entire checkpoint list`, and `entire checkpoint explain <id>`. `--skip-push-sessions` disables automatic session-data pushes. [Official CLI repository](https://github.com/entireio/cli)

Session transcripts can contain prompts, file contents, and tool output; repository readers may access them. Secret redaction is best effort, and image contents are not OCR-scanned for secrets. This matters because the original project PDFs include private correspondence and temporary credentials. [Entire security and privacy](https://github.com/entireio/cli/blob/main/docs/security-and-privacy.md)

The initial inspection did not find `entire` on PATH. Entire remains parked under the [current decision register](../10-decisions.md); do not install, enable, or publish sessions for the selected two-partner path. Revisit only if the user later wants a demonstrated development-trace integration.

## Partner acceptance criteria

1. **Credentials:** Google and Gradium pass authenticated preflight; no secret reaches frontend, AppSpec, firmware, or public logs.
2. **Actual Android recording:** an English recording passes conversion and STT, and its essential rule affects generation.
3. **Formats and failures:** native phone input works; silence, missing audio, malformed files, and incomplete streams produce understandable results.
4. **Observable partner usage:** the selected single-prompt demo performs a real call to both selected providers. Record which STT/TTS path was used; label fallbacks honestly.
5. **One-action completion:** no mandatory transcript, preview, or install reconfirmation appears after Generate and install. The app becomes usable and the exact installed ID/version/hash is acknowledged.
6. **Useful evidence:** connect input, actual providers, AppSpec version, validation results, initial user action, and device ACK using internal job IDs. Never retain keys or authentication headers in the trace.

The ledger records which criteria have actual evidence. Reading documentation alone does not satisfy any authenticated integration or physical-device gate.
