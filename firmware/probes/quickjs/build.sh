#!/usr/bin/env bash
# Standalone cross-build only. This never opens serial or flashes firmware.
set -e
set -o pipefail
project_root="$(cd "$(dirname "$0")/../../.." && pwd)"
export IDF_PATH="$project_root/.tools/esp-idf-v5.5.5"
export IDF_TOOLS_PATH="$project_root/.tools/espressif"
export IDF_TARGET=esp32p4
# The verified component is supplied locally; no component download is needed.
export IDF_COMPONENT_MANAGER=0
. "$IDF_PATH/export.sh"
idf.py -C "$project_root/firmware/probes/quickjs" \
    -B "$project_root/.tools/quickjs-probe/target-build" \
    -D "SDKCONFIG=$project_root/.tools/quickjs-probe/target-sdkconfig" build
