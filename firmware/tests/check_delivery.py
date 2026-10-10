#!/usr/bin/env python3
"""Build and run the actual delivery C state machine with sanitizers.

Transport, persistence fault injection and UI commands are synthetic boundaries;
package decoders and cryptographic hashes are the real shared implementations.
No network, serial access or firmware modification occurs.
"""
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / ".tools/app-ui-host"
CMAKE = ROOT / ".tools/espressif/tools/cmake/3.30.2/CMake.app/Contents/bin/cmake"
NINJA = ROOT / ".tools/espressif/tools/ninja/1.12.1/ninja"
cmake = str(CMAKE) if CMAKE.is_file() else shutil.which("cmake")
ninja = str(NINJA) if NINJA.is_file() else shutil.which("ninja")
if not cmake or not ninja:
    raise SystemExit("Local CMake and Ninja are required")
subprocess.run([cmake, "-S", str(ROOT / "firmware/tests/ui-host"), "-B", str(BUILD),
                "-G", "Ninja", "-DCMAKE_MAKE_PROGRAM=" + ninja,
                "-DCMAKE_BUILD_TYPE=Debug"], check=True, timeout=45)
subprocess.run([cmake, "--build", str(BUILD), "--target", "app_delivery_test",
                "app_ui_test", "-j8"], check=True, timeout=180)
for name in ("app_delivery_test", "app_ui_test"):
    subprocess.run([str(BUILD / name)], check=True, timeout=30)
