#!/usr/bin/env python3
"""Run the companion and a temporary HTTPS tunnel until Ctrl+C.

Creates a local private QR/link page; never prints access tokens. No provider
generation or hardware writes are triggered by starting the service.
"""

import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).absolute().parent.parent
sys.path.insert(0, str(ROOT))
from backend.server import configure, save_private

DIRECTORY = ROOT / "private/service"
URL_PATTERN = re.compile(r"https://[a-z0-9]+(?:-[a-z0-9]+)+\.trycloudflare\.com\b")


def private_write(path, contents):
    descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(contents)


def private_log(path):
    return os.fdopen(os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w")


def alive(process):
    if process.poll() is not None:
        raise RuntimeError("service_process_exited")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


def wait_for_public_service(base_url, opener, processes, timeout=120):
    """A printed tunnel hostname does not establish a working connection."""
    expected = (ROOT / "companion/app.js").read_bytes()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for process in processes:
            alive(process)
        try:
            request = urllib.request.Request(base_url + "/app.js", headers={"Cache-Control": "no-cache"})
            with opener.open(request, timeout=min(8, max(.1, deadline - time.monotonic()))) as response:
                if response.status == 200 and response.read(len(expected) + 1) == expected:
                    return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(.5)
    raise RuntimeError("https_tunnel_not_reachable")


def setup_page(base_url, config):
    link = base_url + "/#token=" + config["session_token"]
    private_write(DIRECTORY / "phone-link.txt", link)
    qr_available = False
    compiler = Path("/usr/bin/swiftc")
    renderer = ROOT / ".tools/private-qr"
    try:
        if compiler.is_file() and (not renderer.is_file() or renderer.stat().st_mtime < (ROOT / "scripts/private_qr.swift").stat().st_mtime):
            subprocess.run([str(compiler), "-module-cache-path", str(ROOT / ".tools/swift-module-cache"),
                            str(ROOT / "scripts/private_qr.swift"), "-o", str(renderer)],
                           capture_output=True, timeout=45, check=True)
        if renderer.is_file():
            subprocess.run([str(renderer), str(DIRECTORY / "phone-link.txt"), str(DIRECTORY / "phone-qr.png")],
                           capture_output=True, timeout=15, check=True)
            os.chmod(str(DIRECTORY / "phone-qr.png"), 0o600)
            qr_available = True
    except (OSError, subprocess.SubprocessError):
        pass  # The private clickable/copyable link remains available.
    page = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="referrer" content="no-referrer">
<title>Private device workspace</title><style>body{font:18px system-ui;background:#101712;color:#f2f5e9;max-width:660px;margin:70px auto;padding:24px}a{color:#d3f58a}img{display:block;width:320px;max-width:90%%;image-rendering:pixelated;background:white;padding:24px;margin:30px 0}code{overflow-wrap:anywhere;font-size:12px}</style>
<h1>Open your workspace</h1><p>Scan this private code with your Android camera.</p>%s
<p><a href="%s">Open the companion on this Mac</a></p><p>Or copy this private link to your phone:</p><code>%s</code>
<p>Keep the demo terminal running. This page contains workspace access; do not publish it.</p></html>""" % (
        '<img src="phone-qr.png" alt="Private workspace QR code">' if qr_available else '', html.escape(link, quote=True), html.escape(link))
    path = DIRECTORY / "open-companion.html"
    private_write(path, page)
    return path, qr_available


def main():
    os.environ["PATH"] = "/opt/homebrew/bin:" + os.environ.get("PATH", "")
    cloudflared = shutil.which("cloudflared")
    if not cloudflared:
        print(json.dumps({"error": "cloudflared_not_installed"}))
        return 1
    config = configure(DIRECTORY)
    processes, logs = [], []
    try:
        log = private_log(DIRECTORY / "server.log")
        logs.append(log)
        server = subprocess.Popen([sys.executable, "-B", "-m", "backend.server"], cwd=str(ROOT), stdout=log, stderr=log)
        processes.append(server)
        deadline = time.monotonic() + 15
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        while True:
            alive(server)
            try:
                request = urllib.request.Request("http://127.0.0.1:8787/api/session", headers={"Authorization": "Bearer " + config["session_token"]})
                with opener.open(request, timeout=2) as response:
                    if response.status == 200:
                        break
            except (urllib.error.URLError, TimeoutError):
                if time.monotonic() > deadline:
                    raise RuntimeError("local_service_not_ready")
                time.sleep(.2)
        log = private_log(DIRECTORY / "tunnel.log")
        logs.append(log)
        # The venue's observed QUIC handshakes fail; TCP/HTTP2 connectivity passed.
        tunnel = subprocess.Popen([cloudflared, "tunnel", "--protocol", "http2", "--url", "http://127.0.0.1:8787", "--no-autoupdate"],
                                  cwd=str(ROOT), stdout=log, stderr=log)
        processes.append(tunnel)
        deadline = time.monotonic() + 60
        while True:
            alive(server)
            alive(tunnel)
            match = URL_PATTERN.search((DIRECTORY / "tunnel.log").read_text(errors="replace"))
            if match:
                base_url = match.group()
                break
            if time.monotonic() > deadline:
                raise RuntimeError("https_tunnel_not_ready")
            time.sleep(.25)
        print(json.dumps({"stage": "checking_public_https"}), flush=True)
        wait_for_public_service(base_url, opener, processes)
        save_private(DIRECTORY / "endpoint.json", {"base_url": base_url})
        page, qr = setup_page(base_url, config)
        print(json.dumps({"service": "running", "public_url": base_url, "private_setup_page": str(page),
                          "qr_available": qr, "provider_generation": "not_tested", "device": "not_tested"}), flush=True)
        subprocess.run(["/usr/bin/open", str(page)], check=False)
        while True:
            alive(server)
            alive(tunnel)
            time.sleep(1)
    except KeyboardInterrupt:
        print(json.dumps({"service": "stopped"}))
        return 0
    except Exception as exc:
        code = str(exc) if type(exc) is RuntimeError else "demo_start_failed"
        print(json.dumps({"error": code}))
        return 1
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        for log in logs:
            log.close()


if __name__ == "__main__":
    sys.exit(main())
