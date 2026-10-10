#!/usr/bin/env python3
"""Identify a unique connected ESP chip with sanitized output.

Default mode does not access hardware. --probe runs an esptool ROM query that
may reset the board or enter its bootloader, but does not write flash.
"""

import argparse
import json
import re
import subprocess
from pathlib import Path

from probe_hardware import serial_candidates


ROOT = Path(__file__).absolute().parent.parent
# Do not resolve this symlink: its venv location selects installed packages.
PYTHON = ROOT / ".tools" / "board-probe" / "bin" / "python"
IDF_PYTHON = ROOT / ".tools/espressif/python_env/idf5.5_py3.9_env/bin/python"
TIMEOUT_SECONDS = 30


def parse_output(output, returncode):
    """Allowlist known chip fields; never expose arbitrary tool output."""
    result = {"status": "query_failed", "error_code": "tool_failed"}
    chip = re.search(
        r"^Chip is (ESP32-(?:P4|C6)) \(revision v([0-9]{1,2}\.[0-9]{1,2})\)\s*$",
        output, re.MULTILINE,
    )
    flash = re.search(r"^Detected flash size: ([0-9]{1,3})(KB|MB)\s*$",
                      output, re.MULTILINE)
    if chip:
        result.update(chip_model=chip.group(1), silicon_revision=chip.group(2))
    if flash:
        result["flash_size"] = flash.group(1) + flash.group(2)
    if returncode == 0 and chip and flash:
        result.update(status="identified", error_code=None)
    elif returncode == 0 and chip:
        unknown = re.search(r"^Detected flash size: Unknown\s*$", output, re.MULTILINE)
        result.update(status="partially_identified", error_code=
                      "flash_size_unknown" if unknown else "flash_size_unrecognized")
    elif returncode == 0:
        result["error_code"] = "unrecognized_identity_output"
    elif any(marker in output.lower() for marker in
             ("permission denied", "operation not permitted")):
        result["error_code"] = "serial_operation_denied"
    elif "no module named esptool" in output.lower():
        result["error_code"] = "esptool_unavailable"
    elif "failed to connect" in output.lower():
        result["error_code"] = "chip_connection_failed"
    return result


def identify(requested=False):
    if not requested:
        return {"status": "not_requested"}
    # IDF's esptool 4.12 adds flash-power handling for the observed P4 rev3.2.
    interpreter = IDF_PYTHON if IDF_PYTHON.is_file() else PYTHON
    if not interpreter.is_file():
        return {"status": "unavailable", "error_code": "venv_python_missing"}
    candidates = serial_candidates()
    if len(candidates) != 1:
        return {"status": "skipped", "error_code": "no_unique_serial_candidate",
                "candidate_count": len(candidates)}
    try:
        result = subprocess.run(
            [str(interpreter), "-I", "-m", "esptool", "--port", candidates[0],
             "--no-stub", "flash_id"],
            capture_output=True, text=True, errors="replace",
            timeout=TIMEOUT_SECONDS, check=False,
        )
    except subprocess.TimeoutExpired:
        return {"status": "timed_out", "error_code": "query_timeout",
                "timeout_seconds": TIMEOUT_SECONDS}
    except OSError:
        return {"status": "unavailable", "error_code": "tool_launch_failed"}
    return parse_output(result.stdout + "\n" + result.stderr, result.returncode)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", action="store_true",
                        help="Run a bounded ROM query; may reset, never writes flash")
    args = parser.parse_args()
    report = identify(args.probe)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] in (
        "not_requested", "identified", "partially_identified") else 1


if __name__ == "__main__":
    raise SystemExit(main())
