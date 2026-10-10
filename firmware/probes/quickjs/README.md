# Isolated QuickJS-NG feasibility probe

This project tests a real JavaScript interpreter for future programmable apps. It is separate from the working AppSpec firmware: there is no production UI binding, app-package loader or device SDK here. The probe never flashes the board, accesses provider/device credentials or changes the main firmware configuration.

## Pinned dependency

The source is the official [Espressif QuickJS-NG 0.14.0 component](https://components.espressif.com/components/espressif/quickjs-ng/versions/0.14.0/readme), which declares IDF >=5.4 and all targets. Its uploaded manifest identifies [esp-iot-solution commit 0d0b99456ce9112f4ac4838927ba837949359f9b](https://github.com/espressif/esp-iot-solution/tree/0d0b99456ce9112f4ac4838927ba837949359f9b/components/quickjs-ng).

- Component hash: `51ead31abca34af01a44df24128e9ea10331cf35beb976a18fae62a03d36d6e2`.
- Downloaded ZIP: 528,960 bytes; SHA256 `bb1d54159574306136d70395a6ce51c998b9b3a0f777fd2fdf53965e4b4aca81`.
- Commit evidence: the registry component hash and archive `repository_info`, not a separate Git checkout verification.

The fetcher bounds HTTPS downloads and archive expansion, rejects unsafe archive entries, checks the exact manifest and uses the installed official component hashing algorithm. Public source is retained under ignored `.tools/quickjs-probe/`, including a download cache for diagnosing failures without downloading again. Source validation precedes compilation. The component's own licenses remain with that dependency; it is not vendored in the public project.

## Run

From the repository root, after the existing IDF5.5.5 toolchain setup:

```sh
python3 -B scripts/probe_programmable_runtime.py
python3 -B scripts/probe_programmable_runtime.py --fetch
python3 -B scripts/probe_programmable_runtime.py --host
python3 -B scripts/probe_programmable_runtime.py --target
python3 -B -m unittest discover -s firmware/probes/quickjs -p 'test_*.py' -v
```

Without flags the helper only verifies local dependency status. `--fetch` explicitly permits the public source download. `--host` compiles with Clang AddressSanitizer/UndefinedBehaviorSanitizer and executes the actual engine. `--target` cross-builds this standalone project for ESP32-P4 revision3 with16MB flash. The script verifies the generated target/IDF/revision configuration before reporting build success. It uses the local verified component directly, with IDF's component manager disabled for this isolated build. It does not flash. Logs and source pins are stored locally with mode0600; the console prints a bounded result.

## Observed results: 10 October 2026

The actual host engine passed1,272 callback checks and100 fresh-app cycles. A closure uses a variable, array and computed color; its native sink verifies each callback's output. Further checks cover syntax/ordinary exceptions, interrupted infinite loops, recursive stack exhaustion, allocation exhaustion, self-rescheduling microtasks and a usable fresh app after each failed runtime. Teardown left zero tracked allocation payload bytes. Peak tracked payload was255,557 bytes. Two executions took approximately60–68ms for the full harness on this Mac, including all cases; these are host observations, not target performance measurements.

The standalone target completed an actual1,073-step compile/link with ESP-IDF5.5.5 and the pinned engine. Generated configuration confirms ESP32-P4, minimum revision300 and16MB flash. The resulting image is761,376 bytes, SHA256 `f82e11bdd72b3390e09569253d5cae2b91bcf2efdc1b2aa2e70e4907c50b5b5b`. **It has not been flashed or executed on the device.** The main runtime and its stored apps are unchanged.

## What this establishes and what remains

The engine can execute ordinary JavaScript callbacks on the host, recover through runtime replacement, and compile for the exact P4 target. It does not yet establish physical target heap use, callback timing, UI behavior, delivery compatibility or peripheral access.

The custom allocator caps tracked allocation payload at512KiB and also sets the engine's256KiB memory limit. Payload accounting excludes allocator headers, allocator overhead and native stack; it is not a measurement of total heap use. The engine stack limit is32KiB. Script interrupt checks use a50ms deadline or1,000 hook calls; these are soft limits at engine interruption points, not guaranteed wall-time bounds for parsing or native calls. Microtask draining is capped at64 jobs and a deadline. A20-second child-process timeout also bounds the host test process.

`std`, `os` and `fetch` are not registered in the test runtime. The sink is a small test callback, not an SDK. This is not process isolation or proof that every conceivable script/resource attack is contained. Production bindings need argument and buffer bounds, app-owned object handles, lifecycle cleanup, bounded native work and one-task engine access. A physical probe and these bindings must pass their own gates before programmable packages replace or accompany AppSpec. Camera, microphone and speaker support is not implemented by embedding the interpreter.

See the [platform plan](../../../docs/15-programmable-apps.md) for the proposed shell, SDK and migration gates, and [probe.c](probe.c) for the executable checks.
