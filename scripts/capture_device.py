#!/usr/bin/env python3
"""Capture a bounded passive UART log; never send bytes or toggle reset lines."""
import argparse
import json
import os
import re
import select
import sys
import termios
import time
from pathlib import Path

ROOT = Path(__file__).absolute().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from probe_hardware import serial_candidates


def summarize(data):
    text = data.decode("utf-8", errors="replace").lower()
    markers = {
        "runtime_ready": "local_runtime_ready",
        "ip_acquired": "got ip",
        "sdio": "sdio",
        "coprocessor": "slave",
        "timeout": "timeout",
        "failure": "failed",
        "tls": "esp-tls",
        "certificate": "certificate",
        "dns_lookup": "getaddrinfo",
        "connection": "connect",
        "time_sync": "sntp",
        "panic": "guru meditation",
        "stack_overflow": "stack overflow",
        "assertion": "assert failed",
    }
    return {"bytes": len(data), "utf8_replacements": text.count("\ufffd"),
            "markers": {key: phrase in text for key, phrase in markers.items()}}


def capture(seconds):
    if not 1 <= seconds <= 30:
        return {"status": "invalid_duration"}
    ports = serial_candidates()
    if len(ports) != 1:
        return {"status": "unique_port_required"}
    fd = None
    data = bytearray()
    code = None
    configured = False
    try:
        fd = os.open(str(ports[0]), os.O_RDONLY | os.O_NONBLOCK | os.O_NOCTTY)
        attrs = termios.tcgetattr(fd)
        attrs[0] &= ~(termios.IGNBRK | termios.BRKINT | termios.PARMRK | termios.ISTRIP |
                      termios.INLCR | termios.IGNCR | termios.ICRNL | termios.IXON)
        attrs[1] &= ~termios.OPOST
        attrs[2] = (attrs[2] & ~(termios.CSIZE | termios.PARENB)) | termios.CS8
        attrs[3] &= ~(termios.ECHO | termios.ECHONL | termios.ICANON | termios.ISIG | termios.IEXTEN)
        attrs[4] = attrs[5] = termios.B115200
        attrs[6][termios.VMIN] = attrs[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
        configured = True
        termios.tcflush(fd, termios.TCIFLUSH)
        print(json.dumps({"stage": "listening", "seconds": seconds}), flush=True)
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline and len(data) < 262144:
            ready, _, _ = select.select([fd], [], [], min(.2, max(0, deadline - time.monotonic())))
            if ready:
                try:
                    chunk = os.read(fd, min(4096, 262144 - len(data)))
                    if not chunk:
                        break
                    data.extend(chunk)
                except BlockingIOError:
                    pass
    except (OSError, termios.error) as error:
        code = error.args[0] if error.args and isinstance(error.args[0], int) else -1
    finally:
        if fd is not None:
            os.close(fd)
    folder = ROOT / "private/board-baseline"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    out = os.open(folder / "runtime-monitor.log", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(out, 0o600)
    with os.fdopen(out, "wb") as stream:
        stream.write(data)
    return {"status": "serial_denied" if code else "captured" if data else "empty",
            "errno": code, "configured_115200": configured, **summarize(data)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", action="store_true", help="Read UART at 115200; no reset or transmitted bytes")
    parser.add_argument("--seconds", type=int, default=10, choices=range(1, 31), metavar="1..30")
    args = parser.parse_args()
    if not args.capture:
        parser.print_help()
        return
    print(json.dumps(capture(args.seconds), indent=2))


if __name__ == "__main__":
    main()
