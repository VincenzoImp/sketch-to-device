"""Real backend restart/SQLite preservation plus local supervisor controls."""

import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

from backend.server import Application, Handler, configure, save_private
from scripts.run_demo import (NoRedirect, restart_backend, restart_request,
                              service_control, stop, wait_local)

ROOT = Path(__file__).resolve().parents[1]


class DemoRestartTests(unittest.TestCase):
    def test_actual_backend_restarts_preserving_config_database_and_external_child(self):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            config = configure(folder)
            with socket.socket() as reserve:
                reserve.bind(("127.0.0.1", 0))
                port = reserve.getsockname()[1]
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
            children = []
            def start():
                process = subprocess.Popen([sys.executable, "-B", "-m", "backend.server", "--data", str(folder),
                                            "--port", str(port)], cwd=str(ROOT), stdout=subprocess.DEVNULL,
                                            stderr=subprocess.DEVNULL)
                children.append(process)
                return process
            # This stand-in represents a separately supervised tunnel process.
            tunnel = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(30)"])
            try:
                holder = [start()]
                wait_local(holder[0], opener, config, port)
                before = (folder / "demo-config.json").read_bytes()
                request = urllib.request.Request("http://127.0.0.1:%d/api/uploads" % port, data=b"retained upload",
                    headers={"Authorization": "Bearer " + config["session_token"], "Content-Type": "image/png"})
                with opener.open(request, timeout=2) as response:
                    upload = json.load(response)["upload_id"]
                previous = holder[0]
                restart_backend(folder, holder, start, opener, config, port)
                self.assertIsNotNone(previous.poll())
                self.assertIsNone(holder[0].poll())
                self.assertIsNone(tunnel.poll())
                self.assertEqual((folder / "demo-config.json").read_bytes(), before)
                self.assertEqual((folder / "uploads" / upload).read_bytes(), b"retained upload")
                with Application(folder).store() as store:
                    self.assertEqual(store._db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            finally:
                for child in children + [tunnel]:
                    stop(child)

    def test_busy_worker_is_not_stopped_or_restarted(self):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            app = Application(folder)
            app.busy = True
            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            server.application = app
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            holder = [SimpleNamespace(poll=lambda: None)]
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
            try:
                with self.assertRaisesRegex(RuntimeError, "generation_in_progress"):
                    restart_backend(folder, holder, lambda: self.fail("Started a child while busy"),
                                    opener, app.config, server.server_port)
                self.assertTrue(app.busy)
            finally:
                server.shutdown(); server.server_close(); thread.join()

    def test_control_matches_current_supervisor_and_returns_result(self):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            launch = "a" * 32
            save_private(folder / "supervisor.json", {"launch_id": launch, "seen_at": time.time()})
            result = []
            thread = threading.Thread(target=lambda: result.append(restart_request(folder, timeout=3)))
            thread.start()
            deadline = time.monotonic() + 2
            calls = []
            while not (folder / "restart-request.json").is_file() and time.monotonic() < deadline:
                time.sleep(.01)
            service_control(folder, launch, lambda: calls.append("restart"))
            thread.join(3)
            self.assertFalse(thread.is_alive())
            self.assertEqual(calls, ["restart"])
            self.assertEqual(result[0]["result"], "backend_restarted")
            self.assertFalse(result[0]["endpoint_changed"])
            save_private(folder / "restart-request.json", {"launch_id": "b" * 32, "request_id": "c" * 32,
                                                          "expires_at": time.time() + 10})
            service_control(folder, launch, lambda: self.fail("Stale supervisor request accepted"))


if __name__ == "__main__":
    unittest.main()
