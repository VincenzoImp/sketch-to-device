"""Negative tests for the isolated public dependency fetcher. No network."""

import importlib.util
import io
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("runtime_probe", ROOT / "scripts/probe_programmable_runtime.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def archive(entries):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as zipped:
        for name, data in entries:
            zipped.writestr(name, data)
    return output.getvalue()


class FetchTests(unittest.TestCase):
    def test_default_absent_is_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory) / "not-created"
            with patch.object(probe, "SOURCE", base / "source"), patch.object(probe, "PIN", base / "pin"):
                self.assertEqual(probe.status()["status"], "dependency_absent")
                self.assertFalse(base.exists())

    def test_exact_registry_version_and_hash(self):
        entry = {"version": "0.14.0", "component_hash": "a" * 64}
        data = {"namespace": "espressif", "name": "quickjs-ng", "versions": [entry]}
        self.assertEqual(probe.registry_hash(json.dumps(data)), "a" * 64)
        for changed in ({"version": "0.14.1"}, {"component_hash": "x" * 64}, {"yanked_at": "today"}):
            with self.subTest(changed=changed):
                data["versions"] = [dict(entry, **changed)]
                with self.assertRaises(probe.ProbeError):
                    probe.registry_hash(json.dumps(data))

    def test_archive_paths_and_links_are_rejected(self):
        link = zipfile.ZipInfo("link")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        bad = [[("../escape", "x")], [("/absolute", "x")], [("a\\b", "x")],
               [("C:/path", "x")], [(link, "../outside")], [("A", "1"), ("a", "2")]]
        for entries in bad:
            with self.subTest(entries=entries), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(probe.ProbeError):
                    probe.extract_archive(archive(entries), Path(directory))

    def test_regular_files_extract_privately_and_expansion_is_bounded(self):
        data = archive([("sub/file.c", "public source")])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            probe.extract_archive(data, root)
            self.assertEqual((root / "sub/file.c").read_text(), "public source")
            self.assertEqual(stat.S_IMODE((root / "sub/file.c").stat().st_mode), 0o600)
        with tempfile.TemporaryDirectory() as directory, patch.object(probe, "MAX_EXPANDED", 1):
            with self.assertRaises(probe.ProbeError):
                probe.extract_archive(data, Path(directory))

    def test_unapproved_redirects_and_credentials_are_rejected(self):
        self.assertTrue(probe.allowed_url(probe.ARCHIVE_URL))
        for url in ("http://components.espressif.com/a", "https://espressif.com.evil/a",
                    "https://user:secret@components.espressif.com/a", "file:///tmp/a",
                    "https://components.espressif.com:444/a", "https://example.org/a"):
            self.assertFalse(probe.allowed_url(url))

    def test_hash_failure_installs_nothing(self):
        metadata = json.dumps({"namespace": "espressif", "name": "quickjs-ng",
                               "versions": [{"version": "0.14.0", "component_hash": "a" * 64}]}).encode()
        data = archive([("quickjs-ng/idf_component.yml", "test")])
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            with patch.object(probe, "BASE", base), patch.object(probe, "SOURCE", base / "engine"), \
                    patch.object(probe, "PIN", base / "pin.json"), \
                    patch.object(probe, "download", side_effect=[metadata, data]), \
                    patch.object(probe, "component_hash", return_value="b" * 64):
                with self.assertRaisesRegex(probe.ProbeError, "registry_hash_mismatch"):
                    probe.fetch()
                self.assertFalse((base / "engine").exists())
                self.assertFalse((base / "pin.json").exists())
                self.assertEqual((base / "download.zip").read_bytes(), data)
                with patch.object(probe, "download", side_effect=AssertionError("must reuse cache")), \
                        patch.object(probe, "component_hash", return_value="a" * 64):
                    self.assertEqual(probe.fetch()["status"], "dependency_verified")
                    self.assertTrue((base / "engine/idf_component.yml").is_file())

    def test_real_installed_verifier_has_phase_specific_errors(self):
        if not probe.IDF_PYTHON.is_file():
            self.skipTest("installed IDF Python unavailable")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            with self.assertRaisesRegex(probe.ProbeError, "component_manifest_missing"):
                probe.component_hash(path)
            (path / "idf_component.yml").write_text("version: 0.14.1\n")
            with self.assertRaisesRegex(probe.ProbeError, "component_manifest_version"):
                probe.component_hash(path)

    def test_target_identity_must_match_actual_header(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(probe, "BASE", Path(directory)):
            build = Path(directory) / "target-build"
            (build / "config").mkdir(parents=True)
            (build / "quickjs_feasibility.bin").write_bytes(b"synthetic image")
            header = build / "config/sdkconfig.h"
            good = ('#define CONFIG_IDF_TARGET "esp32p4"\n'
                    '#define CONFIG_IDF_INIT_VERSION "5.5.5"\n'
                    '#define CONFIG_ESP32P4_REV_MIN_FULL 300\n'
                    '#define CONFIG_ESPTOOLPY_FLASHSIZE_16MB 1\n')
            for wrong in (good.replace('"esp32p4"', '"esp32"'),
                          good.replace('300', '100'), good.replace('5.5.5', '5.4.0'),
                          good.replace('16MB', '4MB')):
                header.write_text(wrong)
                with self.assertRaisesRegex(probe.ProbeError, "target_configuration_mismatch"):
                    probe.target_result()
            header.write_text(good)
            result = probe.target_result()
            self.assertEqual(result["status"], "target_cross_build_passed")
            self.assertFalse(result["physical_execution"])
            self.assertFalse(result["flashed"])


if __name__ == "__main__":
    unittest.main()
