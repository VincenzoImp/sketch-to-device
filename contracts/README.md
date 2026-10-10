# AppSpec v1 executable foundation

This directory freezes the initial host contract and two hand-authored acceptance fixtures. The Python reference validates exact package bytes and executes bounded actions with an injected monotonic clock. It does not render LVGL, install firmware, persist deployment slots, authenticate providers or certify a physical device. Firmware must independently implement and test the same semantics.

The [canonical contract](../docs/04-contracts.md) owns product and transport behavior. The files here make its AppSpec subset executable:

- [app.schema.json](app.schema.json): Draft 2020-12 structural schema, version 1.
- [runtime-capabilities.json](runtime-capabilities.json): runtime 0.2.0 limits, geometry, palettes, optional button color and layout budget, retaining legacy0.1 packages.
- [Tap Sprint](fixtures/tap-sprint.json) and [Focus Timer](fixtures/focus-timer.json): distinct data packages; they are not generated-app evidence.
- [Tap Sprint scenario](scenarios/tap-sprint.json) and [Focus Timer scenario](scenarios/focus-timer.json): data-only traces with explicit expected outcomes.
- [Trusted validator](../runtime/validation.py), [reference state machine](../runtime/reference.py), [scenario runner](../runtime/scenarios.py) and [acceptance tests](../tests/test_contracts.py).

## Run the actual host checks

Requires Python 3.9 or newer and only its standard library. From the repository root:

```sh
python3 -m unittest discover -s tests -p test_contracts.py -v
python3 -m runtime.check contracts/fixtures/tap-sprint.json --scenario contracts/scenarios/tap-sprint.json
python3 -m runtime.check contracts/fixtures/focus-timer.json --scenario contracts/scenarios/focus-timer.json
```

The CLI returns a JSON report and exit status 0 only if its requested checks pass. Failure returns status 1. Its SHA-256 and size identify the exact supplied bytes, including whitespace. Reports explicitly say `host_validation_only`; they contain no device acknowledgment. The implemented backend runs this trusted validator after assigning publication fields and validates the exact bytes it serves.

`parse_app(bytes)` is the untrusted-input entry point. It checks the 65,536-byte and twelve-container limits before decoding an object tree, rejects duplicate keys and non-integer number syntax, then checks structure, typed references, aggregate limits, structural reachability and layout. `validate_app(dict)` assumes the parser already checked byte/depth/duplicate-key constraints. No generic JSON Schema engine is required or bundled. The JSON Schema is a structural interchange artifact; it cannot express every semantic constraint. In particular, JSON Schema's mathematical integer concept can admit `1.0`, while the strict parser rejects fractional/exponent tokens. Both checks are required when another implementation consumes the schema.

## Selected v1 rendering budget

These are conservative layout bounds implemented by the LVGL renderer. Individual generated apps have physical evidence, but the full boundary matrix is not physically qualified: `physical_layout_verified` remains false. Verify worst-case font/wrapping/glyph bounds, hit areas and shell geometry before claiming all accepted layouts render correctly.

- Full display: 320 by 480 portrait. The firmware shell reserves the top 48 pixels. App viewport: origin `(0,48)`, size 320 by 432.
- Theme: exactly `palette` (`dark_green` or `light_blue`) and `font_size` (`medium`). Runtime0.2 additionally accepts an optional button `background_color` in `#RRGGBB` form, selecting black/white text for contrast; it does not enable arbitrary styles or font sizes.
- Supported display text: nonempty printable ASCII U+0020 through U+007E. This deliberately uses a narrower subset than general Latin. Unsupported text fails; it is never silently transliterated. Names have at most 48 characters; other text has at most 120.
- The `medium` font must have size at most 16 pixels, glyph advance at most 16 pixels and a 24-pixel line box. Every line uses fixed character-column wrapping, including spaces, without clipping, scrolling or implicit ellipsis.
- App padding is 16 pixels on every side; title comes first. Each widget has an 8-pixel gap before it. Title/label width is 288 pixels, hence at most 18 characters per line under this budget.
- Other widgets subtract 8-pixel left/right internal padding, leaving 272 pixels (17 characters). Toggles reserve another 32 pixels for their indicator, leaving 240 (15 characters). All non-label widget heights are `max(48, text line height + 16)` pixels. Counters and timers add a 24-pixel numeric line before this formula; absent optional text adds no label line.
- Reject a screen whose title, widgets, gaps and vertical padding exceed 432 pixels. This host arithmetic is a budget check, not proof of physical fit. A runtime font must respect the stated advance bounds; wrapping and measurement cannot merely assume that a nominal 16-pixel font meets them.

The initial implementation also bounds app versions and increment amounts to signed 32-bit positive versions / signed 32-bit amounts. State retains its declared boolean or signed 32-bit integer type. IDs remain globally unique for widgets; screen IDs have their own namespace. All screens must be structurally reachable from the initial screen through button navigation or completion of a timer started by a reachable screen. This graph check does not prove that a requested game is playable; scenario checks establish specific behavior.

## Reference runtime and event semantics

Construct `ReferenceRuntime(raw_bytes, now_ms=0)` and call `advance(now_ms)` whenever the scheduler advances. Integer milliseconds must never move backward. The host tool has no background thread; firmware must drive its real scheduler even when the user is idle.

Capture `event_token()` when a touch event is queued, then pass that token to `press(widget_id, dispatch_ms, token)`. Expired timers are processed before the touch dispatch. Tokens include activation identity and screen-entry sequence; navigation, including navigation to the same screen, package replacement and shell entry/exit invalidate older events. Only currently visible buttons/toggles accept presses.

All widget/timer models exist before the initial screen. Timer completion is ordered by deadline, then ascending widget ID for equal deadlines. Starting an already running or completed timer has no effect; a completed timer requires reset. Paused timers resume their saved remainder. Navigation preserves timer operation; shell entry freezes each running timer and shell exit restores it without counting shell time.

An action list commits state, navigation and timer changes together. Overflow rejects the full action list and records a controlled error. Timer expiry itself is an irreversible scheduler fact: the timer is marked completed once before its handler executes. If that handler overflows, all handler actions roll back, but the timer stays completed and does not repeat. The scenario runner fails whenever a runtime error is recorded.

`install()` validates before replacing the in-memory model; invalid bytes leave it unchanged. Valid replacement resets state and timer models. This is a reference activation operation only: duplicate deployment handling, durable slots, crash recovery and exact device ACKs remain backend/firmware work.

Scenarios contain `scenario_version: 1` and up to 1,000 ordered steps: `press`, `advance`, `enter_shell` or `exit_shell`, each with `at_ms`. Press adds `widget_id`. Optional nonempty `expect` objects assert a subset of the snapshot with exact scalar types; a nested empty object asserts actual emptiness. At least one checkpoint is required. The runner uses fresh tokens; stale-queue cases are covered explicitly by the Python acceptance tests. Shared fixture scenarios certify only their fixed app behavior. Each generated app needs expected outcomes independently derived from the user's request by trusted validation, then checked on its actual returned bytes. Generator-supplied scenarios and reports cannot establish that correctness on their own or replace physical acceptance.

## Observed verification

On 10 October 2026, Python 3.9.6 ran all 33 acceptance tests successfully. Both CLI scenarios passed: Tap Sprint executed seven steps with five checkpoints; Focus Timer executed eight with five checkpoints. Checks cover malformed fields/numbers/references, duplicate keys/IDs, resource boundaries, viewport overflow, atomic action failure, timer order, deadline taps, replay, stale events, shell suspension, invalid replacement and deliberately wrong scenario expectations. Schema identifier/text/name patterns also reject final LF/CR under Python regex checks. A separate JSON Schema engine and the physical display have not been exercised.

## Runtime 0.2.0 extension

Optional button `background_color` accepts exact `#RRGGBB`. The host and device validate the same syntax, and the device selects contrasting black/white text. [Hello Colors](fixtures/hello-colors.json) demonstrates a three-screen finite color cycle using existing navigation. Old packages retain theme colors; no storage migration is required. Native checks are in `firmware/tests/check_colors.py`. Host and native checks do not establish physical color rendering; the updated firmware must be flashed and observed.
