# Shared programmable runtime

Integrated shared host/P4 core for `device-js-1` / `p4-canvas-1`, using the
verified QuickJS-NG0.14.0, LVGL9.4 and IDF5.5.5 sources. Production firmware links
this core; the host reproduction commands below do not flash the device.
The package wire contract and initial
resource profile are owned by [programmable.md](../../contracts/programmable.md)
and [program-profile.json](../../contracts/program-profile.json).

`program_runtime.c` is shared host/P4 C, without any game handlers. Ordinary
JavaScript owns application logic, state and layout. `program_package.c` strictly
decodes the exact schema2 JSON and checks canonical base64 and asset SHA256 using
the installed cJSON/MbedTLS implementations. Input buffers may be released after
parsing; the package owns its JSON tree and decoded RGBA. Runtime creation copies
assets into its own explicit LVGL channel order and does not retain source text.

## Ownership and frames

All runtime calls belong to one serialized owner task/thread. Creation, event
dispatch and destruction execute JavaScript outside the BSP display mutex.
Attach, presentation and detach require that mutex. Attach creates a hidden
320x432 root: the caller decides when to reveal it. The caller must detach before
destroying a runtime, deleting LVGL objects before freeing their pixel storage.
Two RGB565 buffers consume552,960bytes per runtime; batch storage, assets and
JavaScript are additional. Previous/live/candidate can mean three such runtimes.

Native bindings validate primitive arguments and append commands. `gfx.end()`
stages a batch. Only successful completion of the whole callback and Promise
checkpoint makes that batch eligible for presentation. An unfinished batch
leaves the previous complete frame intact. Multiple completed batches in one
checkpoint select the last, while sharing the same command/text/pixel budget.
Nested `begin` is invalid. Caught drawing-budget exhaustion still faults the
runtime. Synchronous exceptions, unhandled rejections, interrupt and microtask
limits latch a fault; later dispatch is refused. A handler may replace itself:
the currently executing callback retains its own duplicated reference.

LVGL draws the completed batch into the back buffer and finishes its draw tasks
before swapping buffers. No JavaScript executes during native rendering. The
renderer uses fixed Montserrat16; unsupported Unicode glyphs use LVGL's missing
glyph behavior, not a promise of universal font coverage. Rectangles/images/text
are clipped by LVGL. Initial line endpoints must be inside the viewport; width
is1..32. Coordinates are bounded integers, colors are exactly`#RRGGBB`.

## Events and clocks

- `app.onTick(fn|null)` receives`{now,delta}` in monotonic milliseconds.
- `app.onPointer(fn|null)` receives`{type,x,y,time}` with down/move/up/cancel and
  app-local coordinates. The caller copies/queues values, coalesces moves and
  protects release/cancel/Home from starvation. This core does not own a queue.
- `app.now()` returns the injected current monotonic milliseconds.
- `app.wallTime()` returns`{epochMs,valid,source}`. Epoch is null when unavailable;
  source is unavailable/estimated/synchronized, and only synchronized is valid.
- `app.random()` and`Math.random()` use the same seeded xorshift32 state. This is
  deterministic application randomness, not cryptography.

Late ticks are supplied once with actual elapsed time, not replayed. Pause skips
ticks/input; resume preserves JS state and resets the delta baseline. Monotonic
time itself continues. Old activation IDs are ignored. The coordinator owns
Home, recovery identity, quarantine and durable delivery; an engine fault alone
does not implement those production transitions. Date/performance intrinsics are
omitted to prevent ambient host time from contaminating deterministic checks.
There are no host OS, filesystem, network or bytecode-loading modules.

## Reproduce the host gate

Prerequisites are the already verified engine source and installed LVGL/IDF
sources used by the earlier public probes. This CMake project does not download
dependencies. Configure with the installed CMake/Ninja, keeping outputs ignored:

```sh
.tools/espressif/tools/cmake/3.30.2/CMake.app/Contents/bin/cmake \
  -S firmware/program_core -B .tools/program-core-host -G Ninja \
  -DCMAKE_MAKE_PROGRAM="$PWD/.tools/espressif/tools/ninja/1.12.1/ninja"
.tools/espressif/tools/cmake/3.30.2/CMake.app/Contents/bin/cmake \
  --build .tools/program-core-host -j8
.tools/program-core-host/program_tests
python3 -B -m unittest firmware.program_core.test_runner -v
```

ASan/UBSan are enabled by default. The native tests cover transactional frames,
computed callbacks, self-replacement, stale activations, pause/time jumps,
exceptions/rejections/loops/memory/stack exhaustion, transparent RGBA corners,
teardown followed by LVGL refresh and100install/dispose cycles. CLI tests run
real subprocesses, validate real frame bytes/hashes and compare malformed wire
packages with the Python validator. These are platform tests, not generated-app
or physical-device evidence.

The fixed host executable accepts only:

```text
program_runner --package exact-package.json --scenario scenario.json --output run-directory
```

The host supplies these paths and an existing private output directory. Scenario
JSON has exactly`version:1`, uint32`seed`, nonnegative`initial_time_ms`,
`wall_time:null` or`{epoch_ms,source}`, and`events`. Events are tick/pause/resume
with`time_ms`; pointer adds`phase,x,y`; frame has`name` instead of time. Names use
the package identifier grammar and must be unique. Timestamps are monotonic;
the maximum span is120,000ms,4,096events and16frames.
The complete serialized scenario is at most524,288bytes, matching the backend
receipt and process-wrapper limit.

A frame event flushes real LVGL output. Files are fixed-index names: tightly
packed little-endian320x432RGB565 and derived binary PPM. JSON stdout reports
exact package hash, frame hashes/names, fixed errors, counts and memory metrics.
Completed exit0 means execution completed, not that every user requirement was
satisfied. Failed execution exits1; invalid command shape exits2. The backend
still enforces process deadlines, restricted environment/output and independent
expected outcomes. Source/scenario errors cannot select arbitrary output paths.

## Bounded exception diagnostics

JavaScript rejections can add a `diagnostic` object to the native result. It has
exactly `phase` (`initialization`, `tick`, or `pointer`), `exception_name`
(printable ASCII, at most48bytes), `message` (printable ASCII, at most192bytes),
`line` and `column` (null or integers1..65536), and boolean `truncated`.
Locations come only from an `app.js` entry within the first1,024bytes of an
own-data stack string. Raw stacks and process stderr are not returned.
The existing fixed `error` remains authoritative; diagnostic text is untrusted
program-authored repair guidance and must never authorize tool operations.

The shared C API offers `pr_create_diagnostic` for failed initialization and
`pr_get_diagnostic` for later callbacks. The existing `pr_create` remains
compatible. Diagnostics latch with the first fault, preserve the prior complete
frame, and do not raise engine/drawing budgets. Native graphics argument errors
name the operation and its actual accepted bounds.

Extraction inspects data descriptors on genuine Error objects, primitive string
throws, and a maximum six non-Proxy ordinary/Error prototype objects for the
name. It does not call getters, `toString`, Proxy traps or custom stack formatters.
Other thrown objects receive a fixed generic hint. Same-turn handled Promise
rejections remain valid; still-unhandled reasons use the same extraction path.
Tests exercise malicious accessors/proxies/coercion, failed callbacks, missing
methods, async rejection, ASCII scrubbing, long strings and source locations.

## Remaining boundaries

Engine limits are256KiB heap,512KiB tracked allocation payload,32KiB JS stack,
soft50ms/1,000interrupt checks and64microtasks per checkpoint. Native drawing is
bounded separately by commands/text/pixel work. Payload accounting excludes
allocator headers, native LVGL objects, drawing scratch, host process overhead,
network/display reserves and other apps. Native LVGL OOM/assertion is **not**
gracefully contained; candidate admission and target headroom must be qualified.
Soft interpreter interrupts are not hard deadlines during parser/native work.
Initialization separates trusted engine/binding setup, source compilation, and
ordinary JavaScript evaluation. Setup no longer consumes the application's
50ms checkpoint. Compilation has a separate50ms soft budget, the existing
source/memory bounds, and an elapsed check after the compiler returns; the
parser is not guaranteed to be preemptible. The interrupt handler is installed
after trusted setup, before compilation. Evaluation and its microtasks start
a fresh unchanged50ms/1,000interrupt/64job checkpoint. Monotonic elapsed time
still includes operating-system preemption; this is not CPU-time accounting.
The local `pr_create_observed` report preserves fixed initialization stage,
elapsed microseconds and interrupt counts even when construction fails.
`startup_tests` uses the real engine and a deterministic test clock to exercise
setup delay, separate compilation/evaluation, compiler expiry and infinite
initialization/callback loops. Device logs also record bounded instance counts
and memory at PREPARE, READY/failure and COMMIT; these are measurements, not an
OOM guarantee.
This slice does not claim thread-safe arbitrary callers, physical frame timing,
complete production lifecycle/rollback, camera/audio support or sandbox perfection.
