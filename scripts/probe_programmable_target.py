#!/usr/bin/env python3
"""Verify dependencies or explicitly cross-build the isolated target UI proof.

No fetch, serial access, flashing, credentials or main firmware/config changes.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "scripts"))
import probe_programmable_ui as ui

PROJECT = ROOT / "firmware/probes/programmable-target-ui"
BASE = ROOT / ".tools/programmable-target-ui-public"
COMPONENTS = ("espressif/cmake_utilities", "espressif/esp_codec_dev", "espressif/esp_lcd_st7796",
              "espressif/esp_lcd_touch", "espressif/esp_lcd_touch_ft5x06",
              "espressif/esp_lvgl_adapter", "waveshare/esp32_p4_wifi6_touch_lcd_3_5")


def status():
    """Read-only integrity checks against the existing engine and component pins."""
    ui.status()
    code = '''import sys
from pathlib import Path
import yaml
from idf_component_tools.hash_tools.validate import validate_hash_eq_hashdir
root=Path(sys.argv[1]); lock=yaml.safe_load((root/'firmware/dependencies.lock').read_text())
for name in sys.argv[2:]:
    path=root/'firmware/managed_components'/name.replace('/', '__')
    assert path.is_dir() and not path.is_symlink()
    assert not any(p.is_symlink() for p in path.rglob('*'))
    pin=lock['dependencies'][name]
    manifest=yaml.safe_load((path/'idf_component.yml').read_text())
    assert str(manifest['version'])==str(pin['version'])
    validate_hash_eq_hashdir(path, pin['component_hash'])
print('verified')
'''
    try:
        checked = subprocess.run([str(ui.engine.IDF_PYTHON), "-c", code, str(ROOT), *COMPONENTS],
                                 capture_output=True, timeout=20, check=False)
    except (OSError, subprocess.SubprocessError):
        raise ui.ProbeError("bsp_verification_unavailable") from None
    if checked.returncode or checked.stdout.strip() != b"verified":
        raise ui.ProbeError("bsp_verification_failed")
    return {"status": "dependencies_verified", "quickjs": "0.14.0", "lvgl": "9.4.0",
            "device_access": False, "production_integrated": False}


def build():
    status()
    for path in (BASE, BASE / "build", BASE / "sdkconfig", BASE / "sdkconfig.old", BASE / "build.log"):
        if path.is_symlink():
            raise ui.ProbeError("unsafe_output_path")
    BASE.mkdir(parents=True, exist_ok=True, mode=0o700)
    log_path = BASE / "build.log"
    with log_path.open("w") as log:
        os.chmod(log_path, 0o600)
        try:
            process = subprocess.Popen(["bash", str(PROJECT / "build.sh")], cwd=ROOT,
                                       stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=True, umask=0o077)
            try:
                process.wait(timeout=420)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
                raise ui.ProbeError("target_build_timeout") from None
        except OSError:
            raise ui.ProbeError("target_build_unavailable") from None
    if process.returncode:
        raise ui.ProbeError("target_build_failed")
    header = (BASE / "build/config/sdkconfig.h").read_text().splitlines()
    required = ('#define CONFIG_IDF_TARGET "esp32p4"', '#define CONFIG_IDF_INIT_VERSION "5.5.5"',
                '#define CONFIG_ESP32P4_REV_MIN_FULL 300', '#define CONFIG_ESPTOOLPY_FLASHSIZE_16MB 1',
                '#define CONFIG_LV_COLOR_DEPTH 16')
    if not all(line in header for line in required):
        raise ui.ProbeError("target_configuration_mismatch")
    raw = (BASE / "build/programmable_target_ui.bin").read_bytes()
    if not raw or len(raw) > 0x400000:
        raise ui.ProbeError("target_binary_invalid")
    return {"status": "target_ui_cross_build_passed", "platform": "esp32p4_rev3",
            "size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
            "binding_sha256": hashlib.sha256((PROJECT / "ui_probe.c").read_bytes()).hexdigest(),
            "flashed": False, "physical_execution": False, "production_integrated": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true", help="build the isolated target proof; never flash")
    args = parser.parse_args(argv)
    try:
        result = build() if args.build else status()
    except (ui.ProbeError, OSError) as error:
        code = str(error) if isinstance(error, ui.ProbeError) else "local_io_failed"
        print(json.dumps({"status": "failed", "error_code": code}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
