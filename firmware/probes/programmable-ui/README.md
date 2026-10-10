# Programmable UI host proof

This reproducible probe binds real QuickJS-NG JavaScript to real LVGL and renders a framebuffer on the host. It is a separate experiment: **it does not change or flash the main firmware, contact providers, install an app package or expose a production SDK**. Its provisional functions are not currently available to generated device apps.

## Prerequisites and run

The tested environment is the project's macOS host with Clang, CMake, Ninja and the installed IDF5.5.5 Python environment. The [engine probe](../quickjs/README.md) must already have verified QuickJS-NG0.14.0 in `.tools/quickjs-probe/`. The main firmware's managed components must already contain LVGL9.4.0. The wrapper does not fetch missing dependencies; it reports a fixed failure code instead.

```sh
python3 -B scripts/probe_programmable_ui.py
python3 -B scripts/probe_programmable_ui.py --run
python3 -B -m unittest discover -s firmware/probes/programmable-ui -p 'test_*.py' -v
```

The default command verifies local dependencies without building or creating output. `--run` performs a bounded sanitizer build and executes the actual checks. Repository paths are derived from the script location. The existing verified QuickJS source is reused. LVGL's manifest commit and complete component hash are checked using the installed official IDF validation algorithm, which excludes generated component metadata appropriately:

- LVGL9.4.0 repository commit: `c016f72d4c125098287be5e83c0f1abed4706ee5`.
- LVGL component hash: `17e68bfd21f0edf4c3ee838e2273da840bf3930e5dbc3bfa6c1190c3aed41f9f`.
- QuickJS-NG source and archive pins remain in the [engine probe](../quickjs/README.md).

No third-party source or binary is vendored here. Build output, logs and framebuffer files stay under ignored `.tools/programmable-ui-public/`. Logs and rendered frames have mode0600. Configure/build/run subprocesses have time limits; a timed-out process group is terminated. The console prints only a checked JSON result, fixed error code and hashes of rendered frames.

## Provisional API and ownership

The experiment supplies `ui.label({x,y,width,height,text,color})`, `ui.button({x,y,width,height,text,background,onClick})` and `ui.update(handle,{text,background,color})`. Each app owns at most32 widgets. Numeric handles are looked up only in that app; native pointers are never returned to JavaScript. Text is at most128 UTF-8 bytes without embedded NUL. Colors are ASCII `#RRGGBB`. Integer geometry must fit the viewport. Updates cannot create objects or change geometry.

Options can have JavaScript getters. Creation decodes all arguments before selecting a widget slot and rechecks capacity after getter execution. Updates validate their values before applying them. Apps have no delete, activation, disposal, filesystem, networking or firmware API in this proof.

The LVGL click callback copies only an activation identity and numeric handle into a24-entry queue. JavaScript runs later in the owner-thread pump. A candidate screen remains unloaded until initialization and bounded pending jobs succeed. Failure discards the candidate while preserving the current screen. Successful activation retains one previous runtime/screen. A callback failure restores that previous app under a fresh activation identity, so old queued messages cannot become valid again. Disposal releases callbacks, objects and the engine.

Unhandled Promise rejections count as failures after each microtask checkpoint. A bounded tracker retains at most16 rejected Promise identities; a catch attached during the same checkpoint is accepted. Tracker overflow fails closed as resource exhaustion. This policy was added after an independent counterexample demonstrated that `JS_ExecutePendingJob` can return success even though an asynchronous callback rejected.

## Actual checks and result

On10October2026, a clean build from this public probe directory compiled the real libraries and binding with AddressSanitizer and UndefinedBehaviorSanitizer. Our C uses strict warnings. The actual run passed:

- 110 successful installs and142 executed callbacks, including100 replacement/disposal cycles.
- 22 rejected initializations,113 stale events discarded and5 intentional queue-overflow drops.
- Zero remaining app models and zero tracked engine-allocation payload after each destroyed runtime.
- Real framebuffer pixels showing pink → blue → green → pink after queued clicks.
- A second JavaScript program using an array, arithmetic, `reduce` and branching to render `Total: 8 | discount`.

The tests exercise ordinary exceptions, infinite loops, microtask starvation, direct/async/Promise callback rejection, same-checkpoint handled rejections, malformed geometry/text/colors, foreign handles, object exhaustion, throwing/reentrant getters and coercion attempts. The original ignored implementation and its Promise correction passed independent review; the public wrapper has additional tests for dependency integrity, partial/invalid results, private logs, process timeout and unsafe output links.

`color-0.ppm` through `color-3.ppm` and `calculation.ppm` are actual software-renderer output. The initial and final pink frames have the same SHA256, `ecde13eb0e5339ae27051a751be772f96ffe61bbf0c904b9bf61678e7582bc11`. These images prove host rendering, not physical display output.

## Limits before production adoption

The proof uses a320×480 host viewport. The current production shell reserves48 pixels, leaving a320×432 app area; this binding cannot be dropped into that shell unchanged. All engine/LVGL/queue access asserts one host owner thread. The actual BSP runs a different task/locking arrangement and needs an explicit integration design.

**Native LVGL allocation failures abort this isolated process.** There is no LVGL heap quota or graceful native out-of-memory recovery. Widget and text limits bound our requests, but they do not establish complete memory containment. ASan/UBSan success is not an exhaustive leak or sandbox proof.

The engine uses a256KiB limit,512KiB tracked allocation-payload cap and32KiB stack limit. Peak per-engine payload was106,466 bytes in the tested host run. That figure excludes allocator headers/overhead, app structures, native stack and LVGL allocations. A staged install may temporarily retain three runtimes. It is not total process or device heap usage.

Execution uses a50ms/1,000-interrupt-check soft budget and a64-job microtask limit. Interrupts occur at engine checkpoints; they do not guarantee a wall-time limit for parsing or native calls. A20-second subprocess limit additionally bounds the host test process. No physical target timing was measured.

These UI bindings have not been cross-built or run on the ESP32-P4. The earlier engine-only P4 build is separate evidence. There are no timers, camera/audio APIs, assets, persistent app state, package validator, delivery/ACK integration or production app library here. Rollback is in-memory UI recovery only. See the [platform plan](../../../docs/15-programmable-apps.md) for the remaining gates.
