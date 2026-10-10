# Runtime and API contracts

AppSpec schema 1; runtime capability version 0.2.0 in current source. Runtime0.2 has been flashed and Hello Colors passed physical checks. These remain legacy contracts; [the redesign plan](16-final-platform-plan.md) defines the future separately versioned programmable path. [Executable host contracts and fixtures](../contracts/README.md) now implement the initial schema, validation and reference behavior; review/test status belongs in [the work ledger](12-work-ledger.md). Embedded validation, backend integration and the LVGL renderer are implemented and independently reviewed; physical integration remains a separate gate. These are product contracts, not provider endpoints or formats. This file owns runtime semantics and product limits; the linked versioned capability file owns concrete presets.

## One-shot generation and install intent

The user selects an already paired device and presses **Generate and install**. This authorizes automatic installation of the resulting validated, reversible data package on that device. Do not require another question, transcript confirmation, or preview approval. Preview is diagnostic output and may also be offered as an optional separate mode.

The request freezes a session/input revision and target `device_id`, with a client idempotency key. The backend verifies pairing at acceptance and again before publishing. It assigns a monotonically increasing intent sequence per device. A job may publish only while its intent remains current; a newer accepted intent prevents an older result from being deployed. Reusing an idempotency key with identical input returns the original job; reusing it with different input fails.

Generation failure leaves the current app untouched. An offline device can receive the package later; the companion remains explicit about waiting. Retry controls may recover a failed operation, but are not mandatory steps in the successful path.

## Canonical project limits

These are prototype budgets, not hardware or provider maxima. Changing them requires updating schema, validators, fixtures, and capability reporting together.

| Resource | v1 limit |
| --- | --- |
| Demo devices | One paired board |
| Generation concurrency | One executing worker. Another request receives `409 generation_busy`; no queue or cancellation API. Reusing an accepted request ID with the same input returns its original job |
| Clip duration | Audio at most 60 seconds; video at most 30 seconds. Enforce the decoded timeline, including durationless browser containers; reject overlong media without silent truncation |
| Backend upload | At most three attachments, 20 MiB each and 32 MiB combined; reject requests above any limit. Photos are decoded and normalized before provider submission; see the media module for pixel/output budgets |
| Prompt | At most 6,000 characters at the companion service boundary |
| Generation job | Default 600 seconds locally, including a ten-second cancellation reserve; 200,000 best-effort tokens per managed interaction. No fixed repair count; stop on the original deadline or second identical artifact hash plus validation failure |
| AppSpec bytes | At most 64 KiB, measured as the actual UTF-8 response body |
| JSON depth | At most 12 nested containers; reject duplicate keys, non-finite numbers, and unknown fields |
| Screens | 1–6, unique IDs |
| Widgets | At most 8 per screen and 32 total; globally unique IDs |
| State | At most 16 declared values: booleans or signed 32-bit integers |
| Actions | At most 4, sequentially, per event |
| Timers | At most 2; integer duration 1–3600 seconds |
| IDs | Lowercase ASCII identifier starting with a letter, then letters/digits/underscore/hyphen; at most 48 characters |
| Display text | Name at most 48 characters; other strings at most 120 characters and 480 UTF-8 bytes; actual layout must also fit |
| Display | Portrait 320 × 480; runtime reports the app viewport remaining after shell controls |

Use byte and depth checks before constructing an unrestricted object tree. The initial executable contract accepts nonempty printable ASCII (U+0020–U+007E), a deliberately narrow English-demo subset; unsupported text is rejected. The selected presets and conservative layout arithmetic are in [runtime capabilities](../contracts/runtime-capabilities.json) and [their explanation](../contracts/README.md). Physical font/rendering verification remains mandatory.

## Deferred ConceptBrief proposal

This object is not implemented or required by the current generation path. The worker combines the frozen prompt, transcript and images directly, with narrow trusted behavior requirements; see [architecture](03-architecture.md). The fields below are a possible later revision/trace format and must not introduce an additional P0 stage or confirmation.

Fields: `brief_version`, `session_id`, `revision`, `language`, `purpose`, `intended_user`, `screens`, `behaviors`, `style`, `constraints`, `assumptions`, `open_questions`, `source_refs`.

Each source reference identifies an attachment or message in the frozen session revision and may include a video timestamp. An optional user-corrected transcript supersedes the automatic transcript in that revision. For conflicts, prefer the latest explicit user instruction, then explicit verbal/text requirements, then visual inference. Record reasonable assumptions for omitted details. `open_questions` is diagnostic metadata; it does not create a required conversation turn. If an essential requirement cannot be represented safely with supported primitives, fail with a useful explanation rather than claiming success or silently changing its meaning.

## AppSpec v1

| Field | Type and constraints |
| --- | --- |
| `schema_version` | Integer, exactly 1 |
| `app_id` | Stable identifier matching the ID rule |
| `version` | Positive increasing signed 32-bit integer assigned by the backend when publishing a new version of that app |
| `name` | UTF-8 display name within the text limit |
| `target` | `{width:320,height:480,orientation:"portrait"}` |
| `theme` | Palette and font-size presets from the frozen runtime capability list |
| `initial_screen` | Existing screen ID |
| `state` | Map of declared and initialized booleans/integers within the state limit |
| `screens` | List of screens within the canonical counts |

A screen has `id`, `title`, and `widgets`. It uses the fixed vertical layout rules; no arbitrary coordinates in v1. A widget has `id`, `type`, and only the fields allowed for that type:

| Widget | Fields and behavior |
| --- | --- |
| `label` | Static `text` |
| `button` | `text`, `on_press` action list, optional `background_color` in exact `#RRGGBB` form; one event per completed tap, no hold-to-repeat |
| `counter` | `state_key` referencing an integer, optional static `text` label |
| `toggle` | `state_key` referencing a boolean, static `text`; one tap toggles that value once |
| `timer` | `duration_seconds`, `on_complete` action list, optional static `text`; displays remaining time when visible |

No arbitrary templates or expressions. The initial capability fixture selects two palettes, one font preset, a 48-pixel shell reservation and 320 × 432 app viewport. Host layout validation accounts for padding, text and usable touch targets; structural widget limits alone do not establish fit. These are implemented budget checks awaiting actual LVGL measurement, not proof of physical rendering.

### Button color and runtime compatibility

Runtime 0.2.0 adds optional button-only `background_color`: six case-insensitive ASCII hex digits after `#`. Nulls, short hex, alpha channels, color names and trailing whitespace are rejected. Omission preserves the selected theme. The renderer chooses black or white text using maximum sRGB relative-luminance contrast. A finite cycle can use existing screen navigation with identical layouts and different button colors; [Hello Colors](../contracts/fixtures/hello-colors.json) exercises pink → blue → green → pink. This adds no scripting or new event action.

New firmware accepts manifests requiring runtime 0.1.0 or 0.2.0 explicitly. The backend labels new packages with its capability version; the old firmware rejects 0.2.0 until upgraded. Saved packages and NVS metadata formats are unchanged; old packages remain valid. Downgrading firmware is not a guarantee that newer colored packages can execute.

### Actions and event ordering

| `type` | Parameters | Rule |
| --- | --- | --- |
| `navigate` | `screen_id` | Existing screen |
| `set` | `state_key`, `value` | Preserve the variable's declared type |
| `increment` | `state_key`, `amount` | Integer variable and signed integer amount; checked 32-bit arithmetic |
| `toggle` | `state_key` | Boolean variable only |
| `timer_start` | `widget_id` | Existing timer; idempotent while running; resumes a paused timer |
| `timer_pause` | `widget_id` | Preserve remaining time; no-op when not running |
| `timer_reset` | `widget_id` | Stop timer and restore its original duration |

Register all widget IDs and timer models from the entire package before rendering `initial_screen`. Timer lifetime does not depend on whether its widget is currently rendered. Rendering a screen reads this existing model; it never recreates or restarts the timer.

Actions execute in their listed order in one serialized runtime event. Evaluate against a small working copy, then commit the state/timer/navigation result together. An invalid operation, including overflow, rejects the entire event without partial state changes and produces a controlled runtime error. Structural errors should already have been rejected by validation.

Use a monotonic clock and a deadline, not a decrement counter tied to rendering frequency. The runtime scheduler processes completion even when there are no taps; before dispatching a user event, it also processes timers due at the current dispatch time. A completed timer fires once, has zero remaining time, and requires `timer_reset` before another start; `timer_start` on a completed timer is a no-op. Expiry remains a completed scheduler fact if its handler overflows: all handler actions roll back and an error is recorded, but the timer does not fire again. For v1, completion handlers may use only `navigate`, `set`, `increment`, and `toggle`, preventing timer restart cycles. If two timers expire together, process by widget ID in ascending order.

Only widgets on the current app screen accept user events. Tag queued events with an app activation ID and a screen-entry sequence, not just a reusable screen ID; ignore stale events after navigation, package replacement, or entry to the shell. This also prevents a queued tap from adding points after a timeout has navigated to the result screen or after a later replay. The game counts taps dispatched before its deadline; taps dispatched at or after the deadline do not count.

Navigating does not pause a timer. Entering the shell suspends app timers and user events; returning restores the saved remaining time and running/paused status without counting time spent in the shell. Installing a different package resets app state. A normal board restart reloads the active package and initializes its variables/timers. Variable persistence is P1; the package itself is persistent.

No general loops, network tools, scripts, file paths, HTML, or executable binaries in AppSpec. Requests outside these capabilities fail with an explanation and a realizable alternative.

### Required 10-second tap-game fixture

This is an acceptance fixture for the runtime, not a hardcoded result to substitute for live generation:

1. `ready`: Start performs `set(score,0)`, `timer_reset(round_timer)`, `timer_start(round_timer)`, then `navigate(play)`.
2. `play`: a counter reads `score`; the tap button increments it by one; `round_timer` has duration 10 seconds and completes with `navigate(result)`.
3. `result`: a counter shows `score`; Play again performs the same four actions as Start.

Required traces: three taps before the deadline yield score 3; a tap at/after the deadline leaves it 3; result appears even without further input; replay starts at score 0 with ten seconds; Start can reach the timer before the play screen has ever been rendered. Also test shell suspension, repeated polling, and stale queued tap events. A headless deterministic behavior simulator and the physical device must exercise the same semantic fixtures and clock rules. An interactive browser preview is P1; if implemented, it also follows these fixtures and is never an extra approval gate.

## Validation

1. Parsing: byte/depth/string/number limits, no unknown fields or duplicate keys.
2. Schema: types, enums, required properties, counts, supported schema and runtime versions.
3. Semantics: references, state types, timer/action restrictions, and reachable screens. Reachability includes navigation from timer completion, not just buttons.
4. Layout: all visible content inside the usable viewport, readable text, and practical touch targets.
5. Scenarios: tap/time traces with expected state and screen transitions, including the user's requested behavior.
6. Device: independently check the package before activation; errors preserve the old app or return to the compiled recovery shell.

Structured model output improves JSON shape but does not establish semantic correctness. The backend applies all checks even when a provider returns valid JSON. A browser preview is not proof of hardware behavior.

## PackageManifest and deployment identity

The backend assigns the final app version, serializes `app.json` once as UTF-8, and computes SHA-256 over the **exact bytes served**. Do not hash a different client serialization. The separate manifest contains `app_id`, `version`, `schema_version`, `sha256`, `size_bytes`, `min_runtime_version`, and a relative download path on the trusted backend. Model-supplied arbitrary URLs or redirects are forbidden.

Backend-owned field assignment must precede the final trusted validation of those exact bytes. Keep the original agent artifact hash as provenance and record a separate final package hash if assignment changed the artifact. A report for different bytes cannot certify the served package.

`GET /api/device/desired` returns `{"desired": null}` or `{"desired": {deployment_id, sequence, manifest}}`. The increasing sequence orders install intents for this device; it is separate from a per-app version. The device rechecks the latest desired identity before committing a downloaded candidate. A superseded candidate is discarded; a failed recheck leaves the existing app active until connectivity recovers.

ACK fields: `device_id`, `deployment_id`, `sequence`, `app_id`, `version`, `sha256`, `status`, optional `error_code`. Device statuses are `downloading`, `validating`, `activating`, `active`, `failed`. The server matches the complete identity; late ACKs remain historical evidence and cannot complete or overwrite the status of a newer deployment.

The device token authenticates the channel. The hash identifies and checks the bytes; it is not an author's digital signature. HTTPS plus backend authorization is sufficient for MVP authenticity; package signatures are a separate future feature.

### Activation, persistence, and recovery

Two data slots and a small versioned metadata record are sufficient; their exact filesystem/NVS implementation must pass interruption tests. Keep package bytes immutable once validated.

1. Download into the inactive slot with a strict byte limit. Finish the write, then reread/check size, hash, schema, references, and resource limits. The existing active package and pointer remain unchanged.
2. Recheck desired deployment identity. Persist a pending-activation record containing candidate and previous slot identities while retaining the previous active pointer.
3. Suspend old app events, initialize the candidate's complete model registry, and prepare its initial view. A controlled failure restores the previous app/shell and records failure for this deployment.
4. Show the candidate and verify that the initial view and runtime event processing are healthy. Commit a single coherent metadata record selecting the candidate, retaining the previous slot, and clearing pending activation. Only then send `active`.
5. On boot, an incomplete pending activation selects the previous validated package, or the compiled shell if there is none. Guard initial UI construction at boot so a repeated construction crash falls back rather than endlessly reopening the same broken package. A completed installation otherwise reloads its active package with fresh app state.

Tests must cover power interruption during download, after pending metadata, and before/after the final pointer commit. The active ACK establishes successful activation and pointer persistence; it does not replace the separate reboot test. A late app error may trigger controlled rollback or the shell; do not claim universal crash recovery before proving it.

Keep deterministic validation/activation failure identities so unchanged polling does not retry a broken package forever; retrying those failures requires an explicit backend retry with a new deployment identity. Transient network/download failures use bounded backoff and may recover under the same deployment identity. If the requested hash/version is already active, acknowledge it without rebuilding UI, resetting timers, or changing score. A lost ACK is resent through later polling/heartbeats. Repeated calls with the same deployment/idempotency key cannot create duplicate installs.

## Implemented internal API

| Method and route | Responsibility |
| --- | --- |
| `GET /api/session` | Session-authenticated paired device, recent connectivity, generation_busy and last exact acknowledged active_app envelope (historical identity, not proof of current physical health) |
| `POST /api/uploads` | Raw bounded media upload; return private attachment identity |
| `POST /api/generate` | Freeze `{prompt, uploads, request_id}` and start the single Generate and install job |
| `GET /api/jobs/{id}` | Session-authenticated progress and exact current deployment state; 404 job_not_found distinguishes a missing saved request from a transient service failure |
| `GET /api/apps/{id}/versions/{version}` | Device-authenticated download of its current desired package |
| `GET /api/device/desired` | Device-authenticated desired envelope or null |
| `POST /api/device/ack` | Device-authenticated full identity/status ACK |

The backend worker publishes automatically after validation. Session creation and one-board binding are private setup operations; public pairing, message-history and arbitrary deployment endpoints are not implemented. Session and device bearer tokens have distinct roles; a client-chosen identifier grants no access. See [the actual handlers](../backend/server.py).

The ACK response includes `deployment_id`, `recorded`, `current_success` and `active_confirmed`. `current_success` describes whether this is the latest desired intent with active deployment state; it is not acceptance of every historical ACK status. `active_confirmed` is true only for an exact `active` ACK matching the device's existing active deployment, session and non-quarantined active row. It can confirm a restored older app without crediting the newer failed job or changing desired/current intent. Firmware checks exact identity and accepts an active receipt when either boolean is true. Both false rejects stale activation; an unknown/malformed receipt retries without reporting success. Legacy three-field responses remain supported through `current_success`. Upgrade the backend before firmware: old firmware treats the additive field as unknown and retries. The candidate's durable active metadata is committed before its active ACK is sent.

## Job states and provenance

Implemented job progress: `queued`, `preparing`, `understanding`, `transcribing`, `generating`, `repairing`, `validating`, `simulating`, `ready`, `failed`, `superseded`; the response becomes `active` only after the exact current device ACK. Deployment states are separate: `queued`, `downloading`, `validating`, `activating`, `active`, `failed`, `superseded`. `ready` means the generated package passed validation; the UI reports App running only for its matching `active` deployment.

The store retains the frozen request hash, job/intent identity, target, sequence, published version, exact bytes/hash and ACK history. The generation CLI saves a sanitized latest-result record; provider versions are fixed in source. Full per-job provider-trace export and measured timing history are not yet implemented. Ordinary logs exclude API keys, audio/base64, passwords, account PDFs, and complete personal content. Expose verifiable actions/results in the UI, not internal chains of thought.
