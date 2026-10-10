#!/usr/bin/env python3
"""Run the companion and a temporary HTTPS tunnel until Ctrl+C.

Creates a local private QR/link page; never prints access tokens. No provider
generation or hardware writes are triggered by starting the service.
"""

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).absolute().parent.parent
sys.path.insert(0, str(ROOT))
from backend.server import configure, generation_gate, save_private

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


def stop(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def local_session(opener, config, port=8787):
    request = urllib.request.Request("http://127.0.0.1:%d/api/session" % port,
        headers={"Authorization": "Bearer " + config["session_token"]})
    with opener.open(request, timeout=2) as response:
        data = json.loads(response.read(65537))
    if data.get("device_id") != config["device_id"]:
        raise RuntimeError("local_service_identity_mismatch")
    return data


def wait_local(server, opener, config, port=8787):
    deadline = time.monotonic() + 15
    while True:
        alive(server)
        try:
            local_session(opener, config, port)
            return
        except (urllib.error.URLError, TimeoutError):
            if time.monotonic() > deadline:
                raise RuntimeError("local_service_not_ready") from None
            time.sleep(.2)


def restart_backend(directory, holder, start, opener, config, port=8787):
    """Retain the tunnel and refuse to interrupt an accepted generation.

    The cross-process lock excludes new acceptance between checking busy and
    stopping the old backend. The supervisor only stops its own child process.
    """
    with generation_gate(directory, exclusive=True):
        if holder[0].poll() is None:
            if local_session(opener, config, port).get("generation_busy") is not False:
                raise RuntimeError("generation_in_progress")
            stop(holder[0])
        holder[0] = start()
        wait_local(holder[0], opener, config, port)


def restart_request(directory, timeout=65):
    """Local control only: no public restart endpoint or signal to arbitrary PIDs."""
    state = json.loads((directory / "supervisor.json").read_text())
    if (time.time() - state.get("seen_at", 0) > 5 or
            not re.fullmatch(r"[a-f0-9]{32}", state.get("launch_id", ""))):
        raise RuntimeError("demo_supervisor_unavailable")
    identifier = uuid.uuid4().hex
    save_private(directory / "restart-request.json", {
        "launch_id": state["launch_id"], "request_id": identifier, "expires_at": time.time() + timeout})
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            result = json.loads((directory / "restart-result.json").read_text())
            if result.get("request_id") == identifier:
                return result
        except (OSError, ValueError):
            pass
        time.sleep(.2)
    raise RuntimeError("backend_restart_unconfirmed")


def service_control(directory, launch_id, restart):
    path = directory / "restart-request.json"
    try:
        request = json.loads(path.read_text())
    except (OSError, ValueError):
        return
    path.unlink()
    if (request.get("launch_id") != launch_id or
            not re.fullmatch(r"[a-f0-9]{32}", request.get("request_id", "")) or
            type(request.get("expires_at")) not in (int, float) or request["expires_at"] < time.time()):
        return
    result = {"request_id": request["request_id"], "result": "backend_restarted", "endpoint_changed": False}
    try:
        restart()
    except Exception as exc:
        result.update(result="restart_failed", error="generation_in_progress" if
                      type(exc) is RuntimeError and str(exc) == "generation_in_progress" else "backend_restart_failed")
    save_private(directory / "restart-result.json", result)


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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restart-backend", action="store_true", help="Load backend changes while keeping the current HTTPS tunnel")
    args = parser.parse_args(argv)
    if args.restart_backend:
        try:
            result = restart_request(DIRECTORY)
            print(json.dumps(result))
            return 0 if result["result"] == "backend_restarted" else 1
        except (OSError, ValueError, RuntimeError):
            print(json.dumps({"result": "restart_failed", "error": "demo_supervisor_unavailable_or_unconfirmed"}))
            return 1
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
        def start_backend():
            child = subprocess.Popen([sys.executable, "-B", "-m", "backend.server"], cwd=str(ROOT), stdout=logs[0], stderr=logs[0])
            processes.append(child)
            return child
        server = start_backend()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        wait_local(server, opener, config)
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
        launch_id, holder = uuid.uuid4().hex, [server]
        while True:
            alive(tunnel)
            # Keep the endpoint alive even if backend startup needs a correction.
            save_private(DIRECTORY / "supervisor.json", {"launch_id": launch_id, "seen_at": time.time(),
                                                        "backend_running": holder[0].poll() is None})
            service_control(DIRECTORY, launch_id,
                            lambda: restart_backend(DIRECTORY, holder, start_backend, opener, config))
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
            stop(process)
        for log in logs:
            log.close()


if __name__ == "__main__":
    sys.exit(main())
