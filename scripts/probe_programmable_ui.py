#!/usr/bin/env python3
"""Verify local dependencies or --run an isolated real QuickJS/LVGL host proof.

No downloads, credentials, device access, flashing or main firmware changes.
Default status is read-only. Build, logs and framebuffer output stay in .tools.
"""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT / "firmware/probes/programmable-ui"
BASE = ROOT / ".tools/programmable-ui-public"
LVGL = ROOT / "firmware/managed_components/lvgl__lvgl"
LVGL_HASH = "17e68bfd21f0edf4c3ee838e2273da840bf3930e5dbc3bfa6c1190c3aed41f9f"
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("engine_probe", ROOT / "scripts/probe_programmable_runtime.py")
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)


class ProbeError(Exception):
    """Fixed non-sensitive failure code."""


def status():
    try:
        result = engine.status()
    except engine.ProbeError:
        raise ProbeError("quickjs_verification_failed") from None
    if result["status"] != "dependency_verified":
        raise ProbeError("quickjs_missing_use_engine_fetch")
    if not LVGL.is_dir() or LVGL.is_symlink():
        raise ProbeError("lvgl_missing_build_main_firmware_first")
    code = '''import sys
from pathlib import Path
import yaml
from idf_component_tools.hash_tools.validate import validate_hash_eq_hashdir
p=Path(sys.argv[1]); m=yaml.safe_load((p/'idf_component.yml').read_text())
assert not any(f.is_symlink() for f in p.rglob('*'))
assert m['version']=='9.4.0'
assert m['repository_info']=={'commit_sha':'c016f72d4c125098287be5e83c0f1abed4706ee5','path':'.'}
validate_hash_eq_hashdir(p, '17e68bfd21f0edf4c3ee838e2273da840bf3930e5dbc3bfa6c1190c3aed41f9f')
print('verified')
'''
    try:
        checked = subprocess.run([str(engine.IDF_PYTHON), "-c", code, str(LVGL)],
                                 capture_output=True, timeout=20, check=False)
        if checked.returncode or checked.stdout.decode().strip() != "verified":
            raise ProbeError("lvgl_verification_failed")
    except (OSError, ValueError, subprocess.SubprocessError):
        raise ProbeError("lvgl_verification_unavailable") from None
    return {"status": "dependencies_verified", "quickjs": "0.14.0", "lvgl": "9.4.0",
            "lvgl_component_hash": LVGL_HASH}


def tool(local, fallback):
    candidate = ROOT / local
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return str(candidate)
    found = shutil.which(fallback)
    if not found:
        raise ProbeError("host_build_tool_missing")
    return found


def execute(command, name, timeout):
    """Bound a process group so a timed-out compiler does not run on alone."""
    path = BASE / name
    if path.is_symlink():
        raise ProbeError("unsafe_output_path")
    with path.open("w") as log:
        os.chmod(path, 0o600)
        try:
            process = subprocess.Popen(command, cwd=BASE, stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=True, umask=0o077)
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
                raise ProbeError("host_process_timeout") from None
        except OSError:
            raise ProbeError("host_process_unavailable") from None
    if process.returncode:
        raise ProbeError("host_process_failed")
    return path


def checked_result(path):
    expected = {"status": "real_ui_probe_passed", "engine": "QuickJS-NG0.14.0", "lvgl": "9.4",
                "installs": 110, "callbacks": 142, "rejected_initializations": 22,
                "stale_events": 113, "dropped_events": 5, "remaining_apps": 0,
                "physical_execution": False}
    try:
        if path.stat().st_size > 4096:
            raise ValueError()
        result = json.loads(path.read_text())
        if (set(result) != set(expected) | {"peak_engine_allocation_payload"}
                or any(result[key] != value or type(result[key]) is not type(value)
                       for key, value in expected.items())
                or type(result["peak_engine_allocation_payload"]) is not int
                or not 0 < result["peak_engine_allocation_payload"] <= 512 * 1024):
            raise ValueError()
    except (OSError, ValueError, KeyError, TypeError):
        raise ProbeError("host_result_invalid") from None
    return result


def run():
    status()
    if BASE.is_symlink():
        raise ProbeError("unsafe_output_path")
    BASE.mkdir(parents=True, exist_ok=True)
    for name in ("build", "color-0.ppm", "color-1.ppm", "color-2.ppm", "color-3.ppm", "calculation.ppm"):
        if (BASE / name).is_symlink():
            raise ProbeError("unsafe_output_path")
    cmake = tool(".tools/espressif/tools/cmake/3.30.2/CMake.app/Contents/bin/cmake", "cmake")
    ninja = tool(".tools/espressif/tools/ninja/1.12.1/ninja", "ninja")
    clang, clangxx = shutil.which("clang"), shutil.which("clang++")
    if not clang or not clangxx:
        raise ProbeError("clang_missing")
    execute([cmake, "-S", str(PROJECT), "-B", str(BASE / "build"), "-G", "Ninja",
             "-DCMAKE_MAKE_PROGRAM=" + ninja, "-DCMAKE_C_COMPILER=" + clang,
             "-DCMAKE_CXX_COMPILER=" + clangxx], "configure.log", 30)
    execute([ninja, "-C", str(BASE / "build"), "-j8"], "build.log", 180)
    result = checked_result(execute([str(BASE / "build/ui_probe")], "run.log", 20))
    # Hash actual renderer output, without publishing screenshots as device proof.
    frames = {}
    for name in ("color-0.ppm", "color-1.ppm", "color-2.ppm", "color-3.ppm", "calculation.ppm"):
        path = BASE / name
        if path.stat().st_size != 460815:
            raise ProbeError("framebuffer_result_invalid")
        os.chmod(path, 0o600)
        frames[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    result.update({"platform": "native_host_asan_ubsan", "framebuffer_sha256": frames,
                   "flashed": False, "production_integrated": False})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="build and run the real host proof; no device access")
    args = parser.parse_args()
    try:
        result = run() if args.run else status()
    except (ProbeError, OSError) as error:
        code = str(error) if isinstance(error, ProbeError) else "local_io_failed"
        print(json.dumps({"status": "failed", "error_code": code}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
