"""Private configuration checks; no actual Wi-Fi reads, build or flashing."""

import contextlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts import provision_device as provision


class ProvisionTests(unittest.TestCase):
    def test_private_atomic_configuration_escapes_values_and_restricts_mode(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "sdkconfig.private"
            target.write_text("old")
            target.chmod(0o644)
            config = {"device_id": "waveshare-p4", "device_token": "T" * 43}
            provision.write_config(target, "https://Demo.EXAMPLE.com:443/", config, 'Name "A" \\ B', 'pass"\\word')
            values = dict(line.split("=", 1) for line in target.read_text().splitlines())
            self.assertEqual(len(values), 5)
            self.assertEqual(json.loads(values["CONFIG_SKETCH_WIFI_SSID"]), 'Name "A" \\ B')
            self.assertEqual(json.loads(values["CONFIG_SKETCH_WIFI_PASSWORD"]), 'pass"\\word')
            self.assertEqual(json.loads(values["CONFIG_SKETCH_BACKEND_URL"]), "https://demo.example.com")
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            self.assertEqual(len(list(Path(folder).iterdir())), 1)

    def test_rejects_url_injection_and_controls_without_overwriting_existing_file(self):
        for url in ["http://example.com", "https://user:password@example.com", "https://example.com/path",
                    "https://example.com?token=PRIVATE", "https://example.com#fragment", "https://example.com\n",
                    "https://example.com:invalid", "https://example.com:65536", "https://bad_host.example"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                provision.backend_url(url)
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "sdkconfig.private"
            target.write_text("unchanged")
            for value in ["SSID\nCONFIG_OTHER=y", "a" * 33, "\x00"]:
                with self.subTest(value=value), self.assertRaises(ValueError):
                    provision.write_config(target, "https://example.com", {"device_id": "p4", "device_token": "T" * 43}, value, "password")
                self.assertEqual(target.read_text(), "unchanged")

    def test_ssid_lookup_accepts_only_valid_actual_network_result(self):
        for stdout, expected in [("Current Wi-Fi Network: Test WiFi\n", "Test WiFi"),
                                 ("You are not associated with an AirPort network.\n", None),
                                 ("Current Wi-Fi Network: hidden\nextra", None)]:
            with patch.object(provision.subprocess, "run", return_value=Mock(returncode=0, stdout=stdout)) as run:
                self.assertEqual(provision.current_ssid(), expected)
                self.assertEqual(run.call_args[0][0], ["/usr/sbin/networksetup", "-getairportnetwork", "en0"])
                self.assertEqual(run.call_args[1]["timeout"], 3)

    def test_main_requires_endpoint_before_creating_tokens_and_never_echoes_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "firmware").mkdir()
            directory = root / "private/service"
            directory.mkdir(parents=True)
            with patch.object(provision, "ROOT", root), patch.object(provision.sys, "argv", ["provision"]), patch.object(provision.sys.stdin, "isatty", return_value=True), patch.object(provision, "configure") as configure, contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(provision.main(), 1)
                configure.assert_not_called()
            (directory / "endpoint.json").write_text('{"base_url":"https://demo.example.com"}')
            with patch.object(provision, "ROOT", root), patch.object(provision.sys, "argv", ["provision"]), patch.object(provision.sys.stdin, "isatty", return_value=True), patch.object(provision, "current_ssid", return_value="PRIVATE_SSID"), patch.object(provision.getpass, "getpass", side_effect=["", "PRIVATE_PASSWORD"]), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(provision.main(), 0)
            report = output.getvalue()
            config = json.loads((directory / "demo-config.json").read_text())
            for secret in ["PRIVATE_SSID", "PRIVATE_PASSWORD", config["device_token"], config["session_token"]]:
                self.assertNotIn(secret, report)
            self.assertTrue(json.loads(report)["configured"])
            self.assertFalse(json.loads(report)["flashed"])


if __name__ == "__main__":
    unittest.main()
