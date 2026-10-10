#!/usr/bin/env bash
# Download tools and build the official display/touch example. Never flash.
set -e
set -o pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
export IDF_TOOLS_PATH="$project_root/.tools/espressif"
export PIP_CACHE_DIR="$project_root/.tools/pip-cache"
export IDF_PATH="$project_root/.tools/esp-idf-v5.5.5"
vendor_dir="$project_root/.tools/waveshare-p4-35"
idf_origin="https://github.com/espressif/esp-idf.git"
vendor_origin="https://github.com/waveshareteam/ESP32-P4-WIFI6-Touch-LCD-3.5.git"
mkdir -p "$IDF_TOOLS_PATH" "$PIP_CACHE_DIR"

check_origin() {
    test -d "$1/.git" || { echo "Existing source is not a Git checkout." >&2; exit 1; }
    test "$(git -C "$1" remote get-url origin)" = "$2" || {
        echo "Existing source has a different origin; refusing to replace it." >&2
        exit 1
    }
}

pin_commit() {
    local actual_commit
    actual_commit="$(git -C "$1" rev-parse HEAD)"
    if test -f "$2"; then
        test "$(cat "$2")" = "$actual_commit" || {
            echo "Source differs from its recorded commit; refusing to continue." >&2
            exit 1
        }
    else
        printf '%s\n' "$actual_commit" > "$2"
    fi
}

if test ! -e "$IDF_PATH"; then
    git clone --branch v5.5.5 --depth 1 --recursive --shallow-submodules \
        "$idf_origin" "$IDF_PATH"
fi
check_origin "$IDF_PATH" "$idf_origin"
test "$(git -C "$IDF_PATH" describe --tags --exact-match HEAD)" = v5.5.5
pin_commit "$IDF_PATH" "$project_root/.tools/esp-idf.commit"
git -C "$IDF_PATH" submodule update --init --recursive --depth 1 --jobs 4

if test ! -e "$vendor_dir"; then
    git clone --depth 1 --filter=blob:none --sparse "$vendor_origin" "$vendor_dir"
fi
check_origin "$vendor_dir" "$vendor_origin"
pin_commit "$vendor_dir" "$project_root/.tools/waveshare.commit"
git -C "$vendor_dir" sparse-checkout set config docs schematic \
    examples/esp-idf/08_lvgl_demo_v9 examples/esp-idf/04_wifistation
git -C "$vendor_dir" checkout --detach

python3 "$IDF_PATH/tools/idf_tools.py" install cmake ninja
"$IDF_PATH/install.sh" esp32p4
. "$IDF_PATH/export.sh"
idf.py --version
cmake --version
ninja --version

# Actual ROM identification established P4 revision 3.2; select it explicitly.
example_dir="$vendor_dir/examples/esp-idf/08_lvgl_demo_v9"
build_args=(-C "$example_dir" -B "$example_dir/build-rev3_x"
    -D "SDKCONFIG=$example_dir/sdkconfig.rev3_x"
    -D WAVESHARE_REVISION_PROFILE=rev3_x)
if test ! -f "$example_dir/sdkconfig.rev3_x"; then
    idf.py "${build_args[@]}" set-target esp32p4
fi
idf.py "${build_args[@]}" build
echo "Build completed. No firmware was flashed; flash capacity remains to verify."
