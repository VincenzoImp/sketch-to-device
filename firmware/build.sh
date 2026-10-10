#!/usr/bin/env bash
# Build only. Secrets belong in ignored sdkconfig.private, never defaults.
set -e
set -o pipefail
project_root="$(cd "$(dirname "$0")/.." && pwd)"
export IDF_TOOLS_PATH="$project_root/.tools/espressif"
export PIP_CACHE_DIR="$project_root/.tools/pip-cache"
export IDF_COMPONENT_CACHE_PATH="$project_root/.tools/component-cache"
export IDF_TARGET=esp32p4
. "$project_root/.tools/esp-idf-v5.5.5/export.sh"
config_path="$project_root/firmware/sdkconfig"
if test -f "$project_root/firmware/sdkconfig.private"; then
    config_path="$project_root/firmware/sdkconfig.private"
fi
python "$project_root/firmware/prepare_config.py" "$config_path" "$project_root/firmware/sdkconfig.defaults"
idf.py -C "$project_root/firmware" -B "$project_root/firmware/build" -D "SDKCONFIG=$config_path" build
