# Isolated programmable UI target proof

This project cross-builds the accepted QuickJS-NG/LVGL experiment for the Waveshare ESP32-P4-WIFI6-Touch-LCD-3.5. It contains two trusted demonstration programs and an intentional asynchronous-failure case. **It does not generate or install user apps, modify the main firmware, access credentials, flash a device or provide a production JavaScript SDK.**

## Reproduce the build

Use the existing project setup: ESP-IDF5.5.5, its tested Python3.9 environment, the verified QuickJS-NG0.14.0 component and the main firmware's pinned managed components. The [engine probe](../quickjs/README.md) and [host UI probe](../programmable-ui/README.md) explain dependency preparation and integrity checks. Missing dependencies must be prepared first; this wrapper does not download anything.

From the repository root, or using the script's absolute path from another directory:

```sh
python3 -B scripts/probe_programmable_target.py
python3 -B scripts/probe_programmable_target.py --build
python3 -B -m unittest discover -s firmware/probes/programmable-target-ui -p 'test_*.py' -v
```

The default command verifies existing dependencies and creates no probe output. The explicit build verifies QuickJS/LVGL through the existing host wrapper, then verifies the BSP, display/touch drivers, adapter, codec and CMake utilities against [the main component lockfile](../../dependencies.lock). It uses the component manager's official hash validator and disables component-manager downloads during compilation. No third-party code is vendored in this directory.

The public CMake project derives repository paths from its own location. The small component alias preserves the accepted FT5x06 dependency name when registry resolution is disabled. SDK configuration, build products and the private build log stay under ignored `.tools/programmable-target-ui-public/`. The wrapper bounds the build to420seconds and terminates its process group on timeout. It emits only fixed status fields and hashes; logs have mode0600. It has no flash or serial option. Do not substitute the main firmware's build or private SDK configuration.

The separate [host CMake project](host/CMakeLists.txt) compiles this same binding with ASan/UBSan, a320×480 RGB565 framebuffer and a320×432 app viewport. It is available for parity checks with Clang/CMake/Ninja and the same local components; host output must also stay under `.tools/`. The original [host UI proof](../programmable-ui/README.md) has its own viewport and evidence and is not silently replaced by this target adapter.

## What the experiment contains

[The binding](ui_probe.c), [allocator](allocator.h), [SDK defaults](sdkconfig.defaults), [partitions](partitions.csv), component alias and host LVGL configuration are byte-identical to the accepted isolated target experiment. The binding SHA256 is `2e00ea6e5a7c493558e89d1ff4664be8473bbbed9fa708e2a51b80e6a9c9efb3`. Only the public CMake repository-relative paths differ from that experiment.

The provisional `ui.label`, `ui.button` and `ui.update` calls support ordinary JavaScript callbacks and state. The Colors program cycles a button through pink, blue and green. Calculator uses an array, arithmetic and branching. A48-pixel system header retains a Home button, with320×432 reserved for app UI. The shell selects either program or an intentional rejected-Promise callback used to exercise previous-app recovery.

One dedicated FreeRTOS task owns every JavaScript runtime operation. BSP callbacks copy value-only events into a24-entry queue; the owner drains it while holding the BSP display mutex. Activation identities reject stale events. A candidate remains hidden until initialization and bounded microtasks pass, and one prior application is retained for callback-failure recovery. The target emits bounded checkpoint counters, heap observations and pump elapsed time; those observations require an actual target run, not merely a successful build.

## Evidence boundaries

The source derives from independently accepted host tests and the isolated target build. On10October2026, the explicit public-path wrapper successfully built ESP32-P4rev3/IDF5.5.5/RGB565 firmware:1,193,968bytes, SHA256`aa36bdd342c24e640dbd96bc45c32a3624a501565f49a87c60c33cfaecc9058a`. The seven copied source/configuration files matched the accepted experiment byte-for-byte; the main private SDK configuration and its existing generated header were unchanged. Four wrapper boundary checks also passed. Independent review of this new wrapper is a separate gate. A matching source hash establishes source identity; a new binary hash records this particular build, including build metadata. Neither proves physical touch, display, memory use, latency or recovery.

**Native LVGL allocation failure is not gracefully contained.** Some allocation paths assert or dereference failure results. The two programs are trusted test inputs; this is not safe admission of arbitrary generated UI. Engine allocation/stack limits, interruption and bounded queues do not establish a quota for every native allocation or a hard deadline for every native call.

There is no production package format, backend generator integration, app delivery/ACK transaction, persistent application state, durable rollback receipt, timers, camera/audio API or asset renderer in this proof. Its partition table matches the isolated experiment but is not permission to flash or alter existing app storage. Physical probing and restoration require a separately reviewed procedure; no such operation is exposed here.
