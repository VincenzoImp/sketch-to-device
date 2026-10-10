#!/usr/bin/env python3
"""Report a sanitized, read-only hardware/toolchain inventory on macOS.

Default: enumerate without opening a serial port. --check-serial-access opens
at most one unambiguous USB serial candidate read-only in a bounded child.
No serial bytes, termios/ioctl changes, reset/flash commands or network calls.
"""

import argparse
import errno
import glob
import importlib.util
import json
import os
import platform
import plistlib
import shutil
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


SERIAL_PATTERNS = (
    "/dev/cu.usbmodem*",
    "/dev/cu.usbserial*",
    "/dev/cu.SLAB_USBtoUART*",
    "/dev/cu.wchusbserial*",
)
TOOLS = ("idf.py", "esptool", "esptool.py", "cmake", "ninja", "clang")


def serial_candidates():
    """Return local paths internally; caller must never include them in output."""
    candidates = set()
    for pattern in SERIAL_PATTERNS:
        for candidate in glob.glob(pattern):
            try:
                if stat.S_ISCHR(os.lstat(candidate).st_mode):
                    candidates.add(candidate)
            except OSError:
                continue
    return sorted(candidates)


def error_result(exc):
    """OSError strings can contain private paths; expose only a known error code."""
    number = getattr(exc, "errno", None)
    return {"status": "denied" if number in (errno.EACCES, errno.EPERM)
            else "error", "errno": number,
            "error_code": errno.errorcode.get(number, "UNKNOWN")}


def serial_worker(candidate):
    """Open/close only: no reads, writes, baud changes, ioctls or protocol probes."""
    if candidate not in serial_candidates():
        return {"status": "candidate_unavailable"}
    descriptor = None
    try:
        descriptor = os.open(candidate, os.O_RDONLY | os.O_NONBLOCK | os.O_NOCTTY)
        return {"status": "opened_read_only"}
    except OSError as exc:
        return error_result(exc)
    finally:
        if descriptor is not None:
            os.close(descriptor)


def serial_access(candidates, requested):
    if not requested:
        return {"status": "not_requested"}
    if len(candidates) != 1:
        return {"status": "skipped_no_unique_candidate"}
    try:
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--serial-worker"],
            input=candidates[0], text=True, capture_output=True, timeout=1.0,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"status": "timed_out", "timeout_seconds": 1}
    except OSError as exc:
        return error_result(exc)
    if result.returncode != 0:
        return {"status": "worker_failed", "exit_code": result.returncode}
    try:
        report = json.loads(result.stdout)
        if (isinstance(report, dict) and
                set(report).issubset({"status", "errno", "error_code"}) and
                report.get("status") in
                {"opened_read_only", "denied", "error", "candidate_unavailable"}):
            return report
    except (ValueError, TypeError):
        pass
    return {"status": "worker_invalid_result"}


def usb_inventory():
    """Count vendor IDs only; omit serial, location, product and personal names."""
    command = "/usr/sbin/ioreg"
    if not Path(command).is_file():
        return {"status": "ioreg_unavailable"}
    try:
        result = subprocess.run(
            [command, "-a", "-r", "-c", "IOUSBHostDevice"],
            capture_output=True, timeout=5, check=False,
        )
        if result.returncode != 0:
            return {"status": "query_failed", "exit_code": result.returncode}
        entries = plistlib.loads(result.stdout)
        ids = []
        for entry in entries:
            if isinstance(entry, dict) and isinstance(entry.get("idVendor"), int):
                ids.append(entry["idVendor"])
        # These counts identify USB vendors, not the connected board or silicon.
        return {"status": "queried", "usb_device_entries": len(entries),
                "espressif_vendor_entries": ids.count(0x303A),
                "wch_vendor_entries": ids.count(0x1A86),
                "silicon_labs_vendor_entries": ids.count(0x10C4)}
    except subprocess.TimeoutExpired:
        return {"status": "timed_out", "timeout_seconds": 5}
    except (OSError, ValueError, plistlib.InvalidFileException, TypeError):
        return {"status": "query_unavailable"}


def inventory(check_serial=False):
    candidates = serial_candidates()
    # Discover only; do not execute arbitrary programs found earlier in PATH.
    available = {name: shutil.which(name) is not None for name in TOOLS}
    module_available = {}
    for module in ("esptool", "serial"):
        try:
            module_available[module] = importlib.util.find_spec(module) is not None
        except (ImportError, ValueError):
            module_available[module] = False
    idf_candidates = [Path.home() / "esp" / "esp-idf", Path("/opt/esp-idf")]
    configured_idf = os.environ.get("IDF_PATH")
    if configured_idf:
        idf_candidates.append(Path(configured_idf))
    return {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "system": platform.system(), "machine": platform.machine(),
        "python_version": platform.python_version(),
        "tools_on_path": available,
        "python_modules_present": module_available,
        "idf_export_found_in_standard_or_configured_location": any(
            (location / "export.sh").is_file() for location in idf_candidates),
        "usb": usb_inventory(),
        "usb_serial_candidate_count": len(candidates),
        "serial_access": serial_access(candidates, check_serial),
        "silicon_revision": "not_probed",
        "peripheral_function": "not_tested",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-serial-access", action="store_true",
                        help="Attempt one bounded read-only open of a unique USB serial candidate")
    parser.add_argument("--serial-worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.serial_worker:
        report = serial_worker(sys.stdin.read(256).strip())
    else:
        report = inventory(args.check_serial_access)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
