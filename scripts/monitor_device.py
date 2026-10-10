#!/usr/bin/env python3
"""Capture an official IDF monitor session with an explicitly requested reset."""
import argparse
import json
import os
import pty
import re
import subprocess
from pathlib import Path

from capture_device import summarize
from identify_board import IDF_PYTHON
from probe_hardware import serial_candidates

ROOT = Path(__file__).absolute().parent.parent


def monitor(seconds=30, reset=False):
    if not reset:
        return {"status": "not_requested"}
    if not 1 <= seconds <= 30:
        return {"status": "invalid_duration"}
    ports = serial_candidates()
    if len(ports) != 1:
        return {"status": "unique_port_required"}
    elf = ROOT / "firmware/build/sketch_to_device.elf"
    if not IDF_PYTHON.is_file() or not elf.is_file():
        return {"status": "monitor_tools_missing"}
    folder = ROOT / "private/board-baseline"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    log = folder / "runtime-idf-monitor.log"
    descriptor = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(descriptor, 0o600)
    command = [str(IDF_PYTHON), "-m", "esp_idf_monitor", "--port", ports[0],
               "--baud", "115200", "--target", "esp32p4", "--disable-address-decoding",
               "--decode-coredumps", "disable", "--decode-panic", "disable",
               "--open-port-attempts", "1", str(elf)]
    # IDF's console reader requires a TTY. The isolated input PTY receives no keys,
    # so the monitor cannot forward user keystrokes or issue console commands.
    master, slave = pty.openpty()
    timed_out = False
    returncode = None
    try:
        print(json.dumps({"stage": "monitor_starting", "reset_requested": True,
                          "seconds": seconds}), flush=True)
        with os.fdopen(descriptor, "wb") as output:
            try:
                result = subprocess.run(command, stdin=slave, stdout=output, stderr=output,
                                        timeout=seconds, check=False)
                returncode = result.returncode
            except subprocess.TimeoutExpired:
                # subprocess.run kills and reaps its child before raising.
                timed_out = True
            except OSError:
                returncode = -1
    finally:
        os.close(slave)
        os.close(master)
    data = log.read_bytes()
    lower = data.lower()
    denied = b"operation not permitted" in lower or b"permission denied" in lower
    diagnostics = {
        "clock_from_build": b"clock_source=build_anchor" in lower,
        "clock_from_rtc": b"clock_source=rtc" in lower,
        "clock_valid": b"clock_valid=1" in lower,
        "clock_unset": b"clock_valid=0" in lower,
        "wifi_ip_ready": b"wifi_ip_ready" in lower,
        "http_failures": sorted(set((stage.decode(), int(status)) for stage, status in
            re.findall(rb"http_failed stage=(open|write|headers|body|complete) status=(-?\d+)", lower))),
        "tls_handshake_errors": sorted(set(code.decode() for code in re.findall(
            rb"mbedtls_ssl_handshake returned (-0x[0-9a-f]{1,8})\b", lower))),
        "tls_certificates": [{"bytes": int(size), "result": int(result), "sha256": digest.decode()}
            for size, result, digest in re.findall(
                rb"tls_certificate bytes=([0-9]{1,6}) result=(-?[0-9]{1,10}) sha256=([a-f0-9]{64}|unavailable)\b",
                lower)[:8]],
    }
    return {"status": "serial_denied" if denied else "capture_complete" if timed_out else "monitor_exited",
            "reset_requested": True, "returncode": returncode, **summarize(data), **diagnostics}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="Start official IDF monitor and reset the board; never flash")
    parser.add_argument("--seconds", type=int, default=30, choices=range(1, 31), metavar="1..30")
    args = parser.parse_args()
    if not args.reset:
        parser.print_help()
        return
    print(json.dumps(monitor(args.seconds, args.reset), indent=2))


if __name__ == "__main__":
    main()
