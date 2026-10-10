#!/usr/bin/env bash
# Isolated build only: no serial, flashing, credentials or main configuration.
set -e
set -o pipefail
project_root="$(cd "$(dirname "$0")/../../.." && pwd)"
export IDF_PATH="$project_root/.tools/esp-idf-v5.5.5"
export IDF_TOOLS_PATH="$project_root/.tools/espressif"
export IDF_TARGET=esp32p4
export IDF_COMPONENT_MANAGER=0
. "$IDF_PATH/export.sh"
idf.py -C "$project_root/firmware/probes/programmable-target-ui" \
    -B "$project_root/.tools/programmable-target-ui-public/build" \
    -D "SDKCONFIG=$project_root/.tools/programmable-target-ui-public/sdkconfig" build
