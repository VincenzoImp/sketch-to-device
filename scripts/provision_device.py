#!/usr/bin/env python3
"""Write private Wi-Fi/service configuration locally; never build or flash."""

import getpass
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit
import warnings

ROOT = Path(__file__).absolute().parent.parent
sys.path.insert(0, str(ROOT))
from backend.server import configure


def kconfig_string(value):
    if type(value) is not str or any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("invalid_configuration")
    return json.dumps(value, ensure_ascii=False)


def backend_url(value):
    if type(value) is not str or not value.isascii() or len(value) > 240 or value != value.strip():
        raise ValueError("invalid_endpoint")
    parsed = urlsplit(value)
    host = parsed.hostname or ""
    if (parsed.scheme != "https" or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment or parsed.path not in ("", "/")
            or any(ord(character) < 33 or ord(character) == 127 for character in value)
            or not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in host.split("."))):
        raise ValueError("invalid_endpoint")
    port = parsed.port
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("invalid_endpoint")
    return "https://" + host + (":" + str(port) if port not in (None, 443) else "")


def current_ssid():
    try:
        result = subprocess.run(["/usr/sbin/networksetup", "-getairportnetwork", "en0"],
                                capture_output=True, text=True, timeout=3, check=False)
        for prefix in ("Current Wi-Fi Network: ", "Current AirPort Network: "):
            line = result.stdout.rstrip("\n")
            if result.returncode == 0 and line.startswith(prefix):
                ssid = line[len(prefix):]
                if 1 <= len(ssid.encode("utf-8")) <= 32 and kconfig_string(ssid):
                    return ssid
    except (OSError, subprocess.SubprocessError, ValueError, UnicodeError):
        pass
    return None


def write_config(target, url, config, ssid, password):
    if not 1 <= len(ssid.encode("utf-8")) <= 32 or len(password.encode("utf-8")) > 64:
        raise ValueError("invalid_wifi")
    device, token = config.get("device_id"), config.get("device_token")
    if (type(device) is not str or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", device)
            or type(token) is not str or not re.fullmatch(r"[a-zA-Z0-9_-]{32,128}", token)):
        raise ValueError("invalid_device_configuration")
    values = {"WIFI_SSID": ssid, "WIFI_PASSWORD": password, "BACKEND_URL": backend_url(url),
              "DEVICE_ID": device, "DEVICE_TOKEN": token}
    raw = "".join("CONFIG_SKETCH_" + key + "=" + kconfig_string(value) + "\n" for key, value in values.items())
    descriptor, temporary = tempfile.mkstemp(prefix="sdkconfig.private.", dir=str(target.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, str(target))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    try:
        if len(sys.argv) != 1 or not sys.stdin.isatty():
            raise ValueError("interactive_terminal_required")
        directory = ROOT / "private/service"
        endpoint = directory / "endpoint.json"
        if endpoint.is_symlink() or not endpoint.is_file() or endpoint.stat().st_size > 4096:
            raise ValueError("start_demo_service_first")
        url = backend_url(json.loads(endpoint.read_text(encoding="utf-8"))["base_url"])
        config = configure(directory)
        default = current_ssid()
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            ssid = getpass.getpass("Wi-Fi SSID" + (" (Enter uses the current Mac network)" if default else "") + ": ")
            password = getpass.getpass("Wi-Fi password (empty for an open network): ")
        write_config(ROOT / "firmware/sdkconfig.private", url, config, ssid or default or "", password)
        print(json.dumps({"configured": True, "wifi_configured": True, "backend_configured": True,
                          "device_configured": True, "built": False, "flashed": False}))
        return 0
    except (Exception, KeyboardInterrupt):
        print(json.dumps({"configured": False, "error": "provisioning_failed",
                          "help": "Keep the demo service running and use an interactive terminal with valid Wi-Fi details."}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
